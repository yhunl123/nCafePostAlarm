import tkinter as tk
from tkinter import ttk, messagebox
import json
import threading
import time
import os
import pygame
import uuid
import sys
import requests
import re
import atexit

# ==========================================
# [설정] 경로 설정
# ==========================================
if getattr(sys, 'frozen', False):
    APP_PATH = os.path.dirname(sys.executable)
else:
    APP_PATH = os.path.dirname(os.path.abspath(__file__))

ALARM_FILE_PATH = os.path.join(APP_PATH, "alarm.mp3")
CONFIG_FILE_PATH = os.path.join(APP_PATH, "config.json")

# ==========================================
# [데이터 관리 클래스]
# ==========================================
class ConfigManager:
    @staticmethod
    def load_config():
        if os.path.exists(CONFIG_FILE_PATH):
            try:
                with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return []
        return []

    @staticmethod
    def save_config(data):
        with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

# ==========================================
# [API 감시 스레드]
# ==========================================
class MonitorThread(threading.Thread):
    def __init__(self, item_id, url, interval, nickname_filter, callback_init, callback_found, callback_error):
        super().__init__()
        self.item_id = item_id
        self.url = url
        self.interval = interval
        self.nickname_filter = nickname_filter

        self.callback_init = callback_init
        self.callback_found = callback_found
        self.callback_error = callback_error

        self.is_running = True
        self.last_article_id = 0
        self.daemon = True

        self.cafe_id, self.menu_id = self.parse_new_cafe_url(url)

    def parse_new_cafe_url(self, url):
        try:
            match = re.search(r'cafes/(\d+)/menus/(\d+)', url)
            if match:
                return match.group(1), match.group(2)
            else:
                return None, None
        except:
            return None, None

    def run(self):
        if not self.cafe_id or not self.menu_id:
            self.callback_error(self.item_id, "URL 분석 실패: cafeId/menuId를 찾을 수 없습니다.")
            return

        try:
            self.last_article_id = self.fetch_latest_article_id()
            self.callback_init(self.item_id, self.last_article_id)
        except Exception as e:
            self.callback_error(self.item_id, f"초기화 실패: {str(e)}")
            return

        while self.is_running:
            for _ in range(self.interval):
                if not self.is_running: break
                time.sleep(1)

            if not self.is_running: break

            try:
                self.check_new_posts()
            except Exception as e:
                # 네트워크 오류 등은 콘솔에만 출력하고 스레드는 유지
                print(f"[{self.item_id}] Check Error: {e}")

    def fetch_latest_article_id(self):
        articles = self.get_article_list_api()
        if articles:
            first_item = articles[0]
            if first_item.get('type') == 'ARTICLE':
                return first_item.get('item', {}).get('articleId', 0)
        return 0

    def get_article_list_api(self):
        api_url = f"https://apis.naver.com/cafe-web/cafe-boardlist-api/v1/cafes/{self.cafe_id}/menus/{self.menu_id}/articles"

        params = {
            'page': 1,
            'pageSize': 15,
            'sortBy': 'TIME',
            'viewType': 'L'
        }

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://cafe.naver.com/'
        }

        response = requests.get(api_url, params=params, headers=headers, timeout=5)
        response.raise_for_status()

        data = response.json()
        article_list = data.get('result', {}).get('articleList', [])
        return article_list

    def check_new_posts(self):
        articles = self.get_article_list_api()

        found_new = False
        max_id_in_page = self.last_article_id

        for entry in reversed(articles):
            if entry.get('type') != 'ARTICLE':
                continue

            item = entry.get('item', {})
            article_id = item.get('articleId')

            if not article_id: continue
            if article_id <= self.last_article_id: continue
            if article_id > max_id_in_page: max_id_in_page = article_id

            writer_info = item.get('writerInfo', {})
            writer_name = writer_info.get('nickname', '')

            if not writer_name:
                writer_name = item.get('writerNickname', '')

            is_match = False
            if not self.nickname_filter:
                is_match = True
            elif self.nickname_filter in writer_name:
                is_match = True

            if is_match:
                found_new = True
                self.callback_found(self.item_id, article_id, writer_name)

        if max_id_in_page > self.last_article_id:
            self.last_article_id = max_id_in_page

    def stop_and_quit_driver(self):
        self.is_running = False

# ==========================================
# [GUI 항목 위젯 클래스]
# ==========================================
class MonitorItemWidget(tk.Frame):
    def __init__(self, parent, data, app_logic):
        super().__init__(parent, bg="white", highlightbackground="black", highlightthickness=1, pady=5)
        self.app_logic = app_logic
        self.data = data
        self.item_id = data['id']

        self.pack(fill="x", pady=2, padx=2)
        self.columnconfigure(1, weight=1)

        # 이름
        self.name_var = tk.StringVar(value=data.get("name", "항목"))
        self.lbl_name = tk.Label(self, textvariable=self.name_var, font=("맑은 고딕", 10, "bold"), bg="white", width=15, anchor="w")
        self.lbl_name.grid(row=0, column=0, padx=10, sticky="w")
        self.lbl_name.bind("<Button-1>", self.enable_edit_name)

        self.ent_name = tk.Entry(self, textvariable=self.name_var, font=("맑은 고딕", 10), width=15)
        self.ent_name.bind("<Return>", self.save_name)
        self.ent_name.bind("<FocusOut>", self.save_name)

        # 상태 메시지
        self.status_var = tk.StringVar(value="대기 중...")
        self.lbl_status = tk.Label(self, textvariable=self.status_var, font=("맑은 고딕", 9), bg="white", anchor="w")
        self.lbl_status.grid(row=0, column=1, padx=5, sticky="ew")

        # 컨트롤
        ctrl_frame = tk.Frame(self, bg="white")
        ctrl_frame.grid(row=0, column=2, padx=5)

        self.btn_stop = tk.Button(ctrl_frame, text="알림끄기", font=("맑은 고딕", 8, "bold"),
                                  bg="#dddddd", fg="black", state="disabled", command=self.stop_alarm)
        self.btn_stop.pack(side="left", padx=5)

        tk.Label(ctrl_frame, text="볼륨", bg="white", font=("맑은 고딕", 8)).pack(side="left")
        self.scale_vol = ttk.Scale(ctrl_frame, from_=0, to=100, orient="horizontal", length=80, command=self.update_volume)
        self.scale_vol.set(data.get("volume", 70))
        self.scale_vol.pack(side="left", padx=5)

        # 우클릭 메뉴
        self.context_menu = tk.Menu(self, tearoff=0)

        self.menu_interval = tk.Menu(self.context_menu, tearoff=0)
        self.interval_var = tk.IntVar(value=data.get("interval", 30))
        for sec in [10, 30, 60, 300, 600]:
            self.menu_interval.add_radiobutton(label=f"{sec}초", variable=self.interval_var, value=sec, command=self.update_interval)
        self.context_menu.add_cascade(label="감시 주기 설정", menu=self.menu_interval)

        self.menu_loop = tk.Menu(self.context_menu, tearoff=0)
        self.loop_var = tk.BooleanVar(value=data.get("loop", True))
        self.menu_loop.add_radiobutton(label="무한 반복", variable=self.loop_var, value=True, command=self.update_loop)
        self.menu_loop.add_radiobutton(label="1회 반복", variable=self.loop_var, value=False, command=self.update_loop)
        self.context_menu.add_cascade(label="알람 반복 설정", menu=self.menu_loop)

        self.context_menu.add_separator()
        self.context_menu.add_command(label="항목 삭제", command=self.delete_item, foreground="red")

        self.bind("<Button-3>", self.show_context_menu)
        self.lbl_name.bind("<Button-3>", self.show_context_menu)
        self.lbl_status.bind("<Button-3>", self.show_context_menu)

    def enable_edit_name(self, event):
        self.lbl_name.grid_remove()
        self.ent_name.grid(row=0, column=0, padx=10, sticky="w")
        self.ent_name.focus_set()

    def save_name(self, event=None):
        new_name = self.name_var.get()
        self.ent_name.grid_remove()
        self.lbl_name.grid()
        self.data['name'] = new_name
        self.app_logic.save_data()

    def update_volume(self, val):
        self.data['volume'] = float(val)
        self.app_logic.save_data()
        self.app_logic.update_realtime_volume(self.item_id, float(val))

    def update_interval(self):
        self.data['interval'] = self.interval_var.get()
        self.app_logic.save_data()
        self.app_logic.restart_thread(self.item_id)

    def update_loop(self):
        self.data['loop'] = self.loop_var.get()
        self.app_logic.save_data()

    def show_context_menu(self, event):
        self.context_menu.post(event.x_root, event.y_root)

    def delete_item(self):
        if messagebox.askyesno("삭제", f"'{self.name_var.get()}' 항목을 삭제하시겠습니까?"):
            self.app_logic.remove_item(self.item_id)

    def stop_alarm(self):
        self.app_logic.stop_alarm(self.item_id)

    def set_status(self, text, is_alarm=False):
        self.status_var.set(text)
        if is_alarm:
            self.lbl_status.config(fg="red", font=("맑은 고딕", 9, "bold"))
            self.config(highlightbackground="red", highlightthickness=2)
            self.btn_stop.config(state="normal", bg="#ffcccc", fg="red")
        else:
            self.lbl_status.config(fg="black", font=("맑은 고딕", 9))
            self.config(highlightbackground="black", highlightthickness=1)
            self.btn_stop.config(state="disabled", bg="#dddddd", fg="black")

# ==========================================
# [메인 애플리케이션 로직]
# ==========================================
class AppLogic:
    def __init__(self, root):
        self.root = root
        self.root.title("네이버 카페 멀티 알리미 (API v2)")
        self.root.geometry("650x500")

        self.items_data = ConfigManager.load_config()
        self.threads = {}
        self.widgets = {}
        self.active_alarms = set()

        pygame.mixer.init()
        self.load_music()
        self.setup_ui()
        self.restore_items()
        self.check_alarm_status()

        atexit.register(self.on_close)

    def load_music(self):
        if os.path.exists(ALARM_FILE_PATH):
            try:
                pygame.mixer.music.load(ALARM_FILE_PATH)
            except Exception as e:
                print(f"Audio Error: {e}")
        else:
            print(f"File Not Found: {ALARM_FILE_PATH}")

    def setup_ui(self):
        top_frame = tk.Frame(self.root, pady=10, padx=10, bg="#f0f0f0")
        top_frame.pack(fill="x")

        tk.Label(top_frame, text="게시판 링크 :", bg="#f0f0f0", font=("맑은 고딕", 10, "bold")).pack(side="left")

        self.entry_url = tk.Entry(top_frame, font=("맑은 고딕", 10))
        self.entry_url.pack(side="left", fill="x", expand=True, padx=10)
        self.entry_url.bind("<Return>", lambda event: self.add_new_item())

        btn_add = tk.Button(top_frame, text="입력", command=self.add_new_item, bg="#4a90e2", fg="white", font=("맑은 고딕", 9, "bold"))
        btn_add.pack(side="left")

        btn_guide = tk.Button(top_frame, text="사용법", command=self.show_guide, bg="#9b59b6", fg="white", font=("맑은 고딕", 9, "bold"))
        btn_guide.pack(side="right", padx=(10, 0))

        list_container = tk.Frame(self.root)
        list_container.pack(fill="both", expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(list_container, bg="white", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="white")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", width=600)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfig(self.canvas.create_window((0,0), window=self.scrollable_frame, anchor='nw'), width=e.width))

    def show_guide(self):
        guide_win = tk.Toplevel(self.root)
        guide_win.title("프로그램 사용법 (상세)")
        guide_win.geometry("600x650") # 창 크기 확대

        # 스크롤 가능한 텍스트 위젯으로 변경
        txt_guide = tk.Text(guide_win, font=("맑은 고딕", 10), padx=20, pady=20, wrap="word")
        scrollbar = ttk.Scrollbar(guide_win, orient="vertical", command=txt_guide.yview)
        txt_guide.configure(yscrollcommand=scrollbar.set)

        txt_guide.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 상세 사용법 내용
        guide_content = """
[ 네이버 카페 멀티 알리미 사용 설명서 ]

■ 1. 기초 설정 (준비하기)
   ① MP3 파일 준비
      - 실행 파일이 있는 폴더에 'alarm.mp3' 파일을 넣어주세요.
      - 이 파일이 알람 소리로 사용됩니다.
   ② 프로그램 실행
      - 알리미 프로그램을 실행합니다.

■ 2. 게시판 등록하기
   ① 링크 복사
      - 네이버 카페에서 감시하려는 게시판에 접속합니다.
      - 브라우저 상단의 주소(URL)를 복사합니다.
      - (예: https://cafe.naver.com/f-e/cafes/12345/menus/12)
   ② 등록
      - 프로그램 상단 입력창에 주소를 붙여넣습니다.
      - [입력] 버튼을 누르거나 엔터키를 칩니다.
      - 하단 리스트에 항목이 추가되면 성공입니다.

■ 3. 항목 관리 (이름 변경/삭제)
   ① 이름 변경
      - 리스트에 추가된 '항목 1' 글자를 클릭합니다.
      - 원하는 이름(예: 팬아트)을 입력하고 엔터를 누릅니다.
   ② 항목 삭제
      - 해당 항목 위에서 [마우스 우클릭]을 합니다.
      - 메뉴 가장 아래의 [항목 삭제]를 클릭합니다.

■ 4. 상세 설정 (우클릭 메뉴)
   - 항목 위에서 [마우스 우클릭] 시 설정 메뉴가 뜹니다.
   
   ① 감시 주기 설정 (기본 30초)
      - 너무 빠르면(10초) 네이버에서 차단될 수 있습니다.
      - 보통 30초를 권장합니다.
   ② 알람 반복 설정
      - [무한 반복]: [알림끄기] 버튼을 누를 때까지 계속 울립니다.
      - [1회 반복]: 알람 소리가 한 번 끝나면 자동으로 멈추고, 
        알림 상태(빨간색)도 자동으로 해제됩니다.

■ 5. 알람 기능 제어
   ① 볼륨 조절
      - 슬라이더를 움직여 각 항목별 알람 소리 크기를 조절합니다.
      - 알람이 울리는 도중에도 즉시 크기가 반영됩니다.
   ② 알림 끄기
      - 알람이 울리면 [알림끄기] 버튼이 활성화됩니다.
      - 버튼을 누르면 소리가 멈추고 다시 감시 모드로 돌아갑니다.

■ 6. 주의 사항
   - '멤버 공개' 게시판은 로그인이 필요하여 감시되지 않을 수 있습니다.
   - 항목을 너무 많이(5개 이상) 추가하면 PC가 느려질 수 있습니다.
        """

        txt_guide.insert("1.0", guide_content)
        txt_guide.config(state="disabled") # 수정 불가능하게 설정

    def add_new_item(self):
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("입력 오류", "URL을 입력해주세요.")
            return

        if not re.search(r'cafes/(\d+)/menus/(\d+)', url):
            messagebox.showerror("입력 오류", "지원하지 않는 URL 형식입니다.\n예시: https://cafe.naver.com/f-e/cafes/123456/menus/12")
            return

        new_data = {
            "id": str(uuid.uuid4()),
            "name": f"항목 {len(self.items_data) + 1}",
            "url": url,
            "interval": 30,
            "loop": True,
            "volume": 70,
            "nickname_filter": ""
        }

        self.items_data.append(new_data)
        self.save_data()
        self.create_item_widget(new_data)
        self.start_thread(new_data)
        self.entry_url.delete(0, tk.END)

    def restore_items(self):
        for data in self.items_data:
            self.create_item_widget(data)
            self.start_thread(data)

    def create_item_widget(self, data):
        widget = MonitorItemWidget(self.scrollable_frame, data, self)
        self.widgets[data['id']] = widget

    def remove_item(self, item_id):
        if item_id in self.threads:
            self.threads[item_id].stop_and_quit_driver()
            del self.threads[item_id]

        if item_id in self.widgets:
            self.widgets[item_id].destroy()
            del self.widgets[item_id]

        self.items_data = [item for item in self.items_data if item['id'] != item_id]
        self.save_data()

        if item_id in self.active_alarms:
            self.active_alarms.remove(item_id)

    def save_data(self):
        ConfigManager.save_config(self.items_data)

    def start_thread(self, data):
        t = MonitorThread(
            data['id'],
            data['url'],
            data['interval'],
            data.get('nickname_filter', ""),
            self.on_thread_init,
            self.on_post_found,
            self.on_thread_error
        )
        self.threads[data['id']] = t
        t.start()

    def restart_thread(self, item_id):
        if item_id in self.threads:
            self.threads[item_id].stop_and_quit_driver()

        for data in self.items_data:
            if data['id'] == item_id:
                self.start_thread(data)
                if item_id in self.widgets:
                    self.widgets[item_id].set_status("재시작 중...")
                break

    def on_thread_init(self, item_id, last_id):
        self.root.after(0, lambda: self._handle_init(item_id, last_id))

    def on_post_found(self, item_id, post_id, writer):
        self.root.after(0, lambda: self._handle_alarm(item_id, post_id))

    def on_thread_error(self, item_id, error_msg):
        self.root.after(0, lambda: self._handle_error(item_id, error_msg))

    def _handle_init(self, item_id, last_id):
        if item_id in self.widgets:
            self.widgets[item_id].set_status(f"API 감시중... (최신: {last_id})", is_alarm=False)

    def _handle_alarm(self, item_id, post_id):
        if item_id in self.widgets:
            msg = f"새 글 감지됨! (ID: {post_id})"
            self.widgets[item_id].set_status(msg, is_alarm=True)
            self.active_alarms.add(item_id)
            self.play_alarm(item_id)

    def _handle_error(self, item_id, msg):
        if item_id in self.widgets:
            short_msg = (msg[:30] + '..') if len(msg) > 30 else msg
            self.widgets[item_id].set_status(f"오류: {short_msg}", is_alarm=False)

    def play_alarm(self, trigger_item_id):
        for data in self.items_data:
            if data['id'] == trigger_item_id:
                vol = data['volume'] / 100.0
                pygame.mixer.music.set_volume(vol)
                break

        if not pygame.mixer.music.get_busy():
            pygame.mixer.music.play()

    def update_realtime_volume(self, item_id, vol_val):
        if item_id in self.active_alarms and pygame.mixer.music.get_busy():
            pygame.mixer.music.set_volume(vol_val / 100.0)

    def stop_alarm(self, item_id):
        if item_id in self.active_alarms:
            self.active_alarms.remove(item_id)

        if item_id in self.widgets:
            current_last_id = 0
            if item_id in self.threads:
                current_last_id = self.threads[item_id].last_article_id
            self.widgets[item_id].set_status(f"API 감시중... (최신: {current_last_id})", is_alarm=False)

        if not self.active_alarms:
            pygame.mixer.music.stop()

    # [수정 15차] 알람 상태 체크 로직 개선
    def check_alarm_status(self):
        # 음악이 멈췄는데(재생 끝), 활성 알람 리스트에 무언가 남아있다면?
        if not pygame.mixer.music.get_busy() and self.active_alarms:

            # 1. 종료된 알람들 중 '1회 재생'인 것들을 찾아 UI 리셋
            # (active_alarms 복사본을 만들어 순회하면서 원본 수정)
            active_list_copy = list(self.active_alarms)
            has_looper = False

            for item_id in active_list_copy:
                item_data = next((item for item in self.items_data if item['id'] == item_id), None)

                if item_data:
                    if item_data['loop']:
                        # 무한반복 항목이면 유지
                        has_looper = True
                    else:
                        # [핵심] 1회 재생 항목이면 음악이 끝났으므로 '알람 끄기' 동작 수행
                        self.stop_alarm(item_id)
                else:
                    # 데이터가 없는 경우(삭제됨 등) 안전하게 제거
                    self.active_alarms.discard(item_id)

            # 2. 아직도 '무한반복' 알람이 남아있다면 다시 재생
            if has_looper:
                # 볼륨 재설정 (남아있는 알람 중 하나 기준)
                target_vol = 0.5
                for item_id in self.active_alarms:
                    d = next((item for item in self.items_data if item['id'] == item_id), None)
                    if d and d['loop']:
                        target_vol = d['volume'] / 100.0
                        break # 하나만 찾으면 됨

                pygame.mixer.music.set_volume(target_vol)
                pygame.mixer.music.play()

        self.root.after(500, self.check_alarm_status)

    def on_close(self):
        for t in self.threads.values():
            t.stop_and_quit_driver()
        try:
            self.root.destroy()
        except:
            pass

if __name__ == "__main__":
    root = tk.Tk()
    app = AppLogic(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()