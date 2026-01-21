import tkinter as tk
from tkinter import ttk, messagebox
import json
import threading
import time
import os
import pygame
import uuid
from functools import partial
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================
# [설정] 실행 파일/스크립트 위치 기준 경로 설정
# ==========================================
import sys
if getattr(sys, 'frozen', False):
    APP_PATH = os.path.dirname(sys.executable)
else:
    APP_PATH = os.path.dirname(os.path.abspath(__file__))

ALARM_FILE_PATH = os.path.join(APP_PATH, "alarm.mp3")
CONFIG_FILE_PATH = os.path.join(APP_PATH, "config.json")

# ==========================================
# [데이터 관리 클래스] 설정 저장/로드
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
# [개별 감시 스레드 클래스]
# ==========================================
class MonitorThread(threading.Thread):
    def __init__(self, item_id, url, interval, nickname_filter, callback_found, callback_error):
        super().__init__()
        self.item_id = item_id
        self.url = url
        self.interval = interval
        self.nickname_filter = nickname_filter
        self.callback_found = callback_found
        self.callback_error = callback_error
        self.is_running = True
        self.driver = None
        self.last_article_id = 0
        self.daemon = True

    def run(self):
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)

            # 초기 접속
            self.driver.get(self.url)
            time.sleep(2)
            self.last_article_id = self.get_latest_post_id()

            # 초기화 완료 신호 (콘솔용)
            print(f"[{self.item_id}] Init Complete. Last ID: {self.last_article_id}")

            while self.is_running:
                time.sleep(self.interval)
                if not self.is_running: break

                try:
                    self.driver.refresh()
                    time.sleep(2)
                    self.check_new_posts()
                except Exception as e:
                    self.callback_error(self.item_id, str(e))

        except Exception as e:
            self.callback_error(self.item_id, str(e))
        finally:
            if self.driver:
                self.driver.quit()

    def stop(self):
        self.is_running = False

    def get_latest_post_id(self):
        try:
            self.driver.switch_to.frame("cafe_main")
        except:
            pass

        # DOM 구조에 따라 가장 최신 글 번호 찾기 (공지 제외)
        try:
            rows = self.driver.find_elements(By.CSS_SELECTOR, "div.article-board table tbody tr")
            for row in rows:
                try:
                    num_txt = row.find_element(By.CSS_SELECTOR, "td.type_articleNumber").text.strip()
                    if num_txt.isdigit():
                        return int(num_txt)
                except:
                    continue
        except:
            pass
        return 0

    def check_new_posts(self):
        try:
            self.driver.switch_to.frame("cafe_main")
        except:
            pass

        rows = self.driver.find_elements(By.CSS_SELECTOR, "div.article-board table tbody tr")
        found_new = False
        max_id_in_page = self.last_article_id

        for row in rows:
            try:
                try:
                    num_element = row.find_element(By.CSS_SELECTOR, "td.type_articleNumber")
                except: continue

                num_txt = num_element.text.strip()
                if not num_txt.isdigit(): continue

                current_id = int(num_txt)
                if current_id <= self.last_article_id: break
                if current_id > max_id_in_page: max_id_in_page = current_id

                # 닉네임 필터링 (없으면 통과)
                writer_text = ""
                try:
                    writer_text = row.find_element(By.CSS_SELECTOR, "td.td_name").text.strip()
                except: pass

                is_match = False
                if not self.nickname_filter: is_match = True
                elif self.nickname_filter in writer_text: is_match = True

                if is_match:
                    found_new = True
                    # 콜백 호출 (메인 스레드로 알림)
                    self.callback_found(self.item_id, current_id, writer_text)

            except: continue

        if max_id_in_page > self.last_article_id:
            self.last_article_id = max_id_in_page

# ==========================================
# [GUI 항목 위젯 클래스]
# ==========================================
class MonitorItemWidget(tk.Frame):
    def __init__(self, parent, data, app_logic):
        super().__init__(parent, bg="white", highlightbackground="black", highlightthickness=1, pady=5)
        self.app_logic = app_logic
        self.data = data # {id, name, url, interval, loop, volume, nickname}
        self.item_id = data['id']

        self.pack(fill="x", pady=2, padx=2)

        # 그리드 설정
        self.columnconfigure(1, weight=1) # 상태 메시지 영역 늘리기

        # 1. 항목 이름 (클릭 시 수정 가능)
        self.name_var = tk.StringVar(value=data.get("name", "항목"))
        self.lbl_name = tk.Label(self, textvariable=self.name_var, font=("맑은 고딕", 10, "bold"), bg="white", width=15, anchor="w")
        self.lbl_name.grid(row=0, column=0, padx=10, sticky="w")
        self.lbl_name.bind("<Button-1>", self.enable_edit_name)

        self.ent_name = tk.Entry(self, textvariable=self.name_var, font=("맑은 고딕", 10), width=15)
        self.ent_name.bind("<Return>", self.save_name)
        self.ent_name.bind("<FocusOut>", self.save_name)

        # 2. 상태 메시지
        self.status_var = tk.StringVar(value="초기화 중...")
        self.lbl_status = tk.Label(self, textvariable=self.status_var, font=("맑은 고딕", 9), bg="white", anchor="w")
        self.lbl_status.grid(row=0, column=1, padx=5, sticky="ew")

        # 3. 우측 컨트롤 패널 (알람끄기, 볼륨)
        ctrl_frame = tk.Frame(self, bg="white")
        ctrl_frame.grid(row=0, column=2, padx=5)

        self.btn_stop = tk.Button(ctrl_frame, text="알림끄기", font=("맑은 고딕", 8, "bold"),
                                  bg="#dddddd", fg="black", state="disabled", command=self.stop_alarm)
        self.btn_stop.pack(side="left", padx=5)

        tk.Label(ctrl_frame, text="볼륨", bg="white", font=("맑은 고딕", 8)).pack(side="left")
        self.scale_vol = ttk.Scale(ctrl_frame, from_=0, to=100, orient="horizontal", length=80, command=self.update_volume)
        self.scale_vol.set(data.get("volume", 70))
        self.scale_vol.pack(side="left", padx=5)

        # 4. 우클릭 메뉴
        self.context_menu = tk.Menu(self, tearoff=0)

        # 감시 주기 서브메뉴
        self.menu_interval = tk.Menu(self.context_menu, tearoff=0)
        self.interval_var = tk.IntVar(value=data.get("interval", 30))
        for sec in [10, 30, 60, 300, 600]:
            self.menu_interval.add_radiobutton(label=f"{sec}초", variable=self.interval_var, value=sec, command=self.update_interval)
        self.context_menu.add_cascade(label="감시 주기 설정", menu=self.menu_interval)

        # 알람 반복 서브메뉴
        self.menu_loop = tk.Menu(self.context_menu, tearoff=0)
        self.loop_var = tk.BooleanVar(value=data.get("loop", True))
        self.menu_loop.add_radiobutton(label="무한 반복", variable=self.loop_var, value=True, command=self.update_loop)
        self.menu_loop.add_radiobutton(label="1회 반복", variable=self.loop_var, value=False, command=self.update_loop)
        self.context_menu.add_cascade(label="알람 반복 설정", menu=self.menu_loop)

        self.context_menu.add_separator()
        self.context_menu.add_command(label="항목 삭제", command=self.delete_item, foreground="red")

        # 이벤트 바인딩 (전체 영역 우클릭)
        self.bind("<Button-3>", self.show_context_menu)
        self.lbl_name.bind("<Button-3>", self.show_context_menu)
        self.lbl_status.bind("<Button-3>", self.show_context_menu)

    # --- 기능 메서드 ---
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
        # 현재 알람이 울리는 중이라면 볼륨 즉시 적용은 AppLogic에서 처리됨

    def update_interval(self):
        self.data['interval'] = self.interval_var.get()
        self.app_logic.save_data()
        self.app_logic.restart_thread(self.item_id) # 주기 변경 시 스레드 재시작 필요

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

    # --- 외부 호출용 ---
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
        self.root.title("네이버 카페 멀티 알리미")
        self.root.geometry("650x500")

        # 데이터 초기화
        self.items_data = ConfigManager.load_config()
        self.threads = {} # {id: MonitorThread}
        self.widgets = {} # {id: MonitorItemWidget}
        self.active_alarms = set() # 알람이 울리고 있는 item_id 집합

        # 오디오 초기화
        pygame.mixer.init()
        self.load_music()

        # UI 구성
        self.setup_ui()

        # 저장된 항목들 복구
        self.restore_items()

        # 알람 루프 시작
        self.check_alarm_status()

    def load_music(self):
        if os.path.exists(ALARM_FILE_PATH):
            try:
                pygame.mixer.music.load(ALARM_FILE_PATH)
            except Exception as e:
                print(f"Audio Error: {e}")
        else:
            print(f"File Not Found: {ALARM_FILE_PATH}")

    def setup_ui(self):
        # 1. 상단 입력바
        top_frame = tk.Frame(self.root, pady=10, padx=10, bg="#f0f0f0")
        top_frame.pack(fill="x")

        tk.Label(top_frame, text="게시판 링크 :", bg="#f0f0f0", font=("맑은 고딕", 10, "bold")).pack(side="left")

        self.entry_url = tk.Entry(top_frame, font=("맑은 고딕", 10))
        self.entry_url.pack(side="left", fill="x", expand=True, padx=10)

        btn_add = tk.Button(top_frame, text="입력", command=self.add_new_item, bg="#4a90e2", fg="white", font=("맑은 고딕", 9, "bold"))
        btn_add.pack(side="left")

        # 2. 메인 리스트 (스크롤 가능)
        list_container = tk.Frame(self.root)
        list_container.pack(fill="both", expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(list_container, bg="white", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="white")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", width=600) # width는 동적 조정 필요할 수 있음
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # 캔버스 폭에 맞춰 프레임 리사이즈
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfig(self.canvas.create_window((0,0), window=self.scrollable_frame, anchor='nw'), width=e.width))

    def add_new_item(self):
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("입력 오류", "URL을 입력해주세요.")
            return

        new_data = {
            "id": str(uuid.uuid4()),
            "name": f"항목 {len(self.items_data) + 1}",
            "url": url,
            "interval": 30,
            "loop": True,
            "volume": 70,
            "nickname_filter": "" # 필요하면 추후 UI에 추가
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
        # 1. 스레드 중지
        if item_id in self.threads:
            self.threads[item_id].stop()
            del self.threads[item_id]

        # 2. UI 삭제
        if item_id in self.widgets:
            self.widgets[item_id].destroy()
            del self.widgets[item_id]

        # 3. 데이터 삭제
        self.items_data = [item for item in self.items_data if item['id'] != item_id]
        self.save_data()

        # 4. 알람 상태 해제
        if item_id in self.active_alarms:
            self.active_alarms.remove(item_id)

    def save_data(self):
        ConfigManager.save_config(self.items_data)

    # --- 스레드 관리 ---
    def start_thread(self, data):
        t = MonitorThread(
            data['id'],
            data['url'],
            data['interval'],
            data.get('nickname_filter', ""),
            self.on_post_found,
            self.on_thread_error
        )
        self.threads[data['id']] = t
        t.start()
        if data['id'] in self.widgets:
            self.widgets[data['id']].set_status("감시 시작 (초기화 중)...")

    def restart_thread(self, item_id):
        if item_id in self.threads:
            self.threads[item_id].stop()

        # 데이터 찾아서 재시작
        for data in self.items_data:
            if data['id'] == item_id:
                self.start_thread(data)
                break

    # --- 콜백 메서드 (스레드에서 호출됨) ---
    def on_post_found(self, item_id, post_id, writer):
        # UI 업데이트는 메인 스레드에서
        self.root.after(0, lambda: self._handle_alarm(item_id, post_id))

    def on_thread_error(self, item_id, error_msg):
        self.root.after(0, lambda: self._handle_error(item_id, error_msg))

    def _handle_alarm(self, item_id, post_id):
        if item_id in self.widgets:
            msg = f"새 글 감지됨! (ID: {post_id})"
            self.widgets[item_id].set_status(msg, is_alarm=True)
            self.active_alarms.add(item_id)
            self.play_alarm(item_id)

    def _handle_error(self, item_id, msg):
        if item_id in self.widgets:
            # 에러 메시지가 너무 길면 자름
            short_msg = (msg[:30] + '..') if len(msg) > 30 else msg
            self.widgets[item_id].set_status(f"오류: {short_msg}", is_alarm=False)

    # --- 알람 및 오디오 제어 ---
    def play_alarm(self, trigger_item_id):
        # 가장 최근에 울린 항목의 볼륨을 따름
        for data in self.items_data:
            if data['id'] == trigger_item_id:
                vol = data['volume'] / 100.0
                pygame.mixer.music.set_volume(vol)
                break

        if not pygame.mixer.music.get_busy():
            pygame.mixer.music.play()

    def stop_alarm(self, item_id):
        if item_id in self.active_alarms:
            self.active_alarms.remove(item_id)

        if item_id in self.widgets:
            self.widgets[item_id].set_status("감시 중... (알람 확인됨)", is_alarm=False)

        # 더 이상 활성화된 알람이 없으면 소리 끄기
        if not self.active_alarms:
            pygame.mixer.music.stop()

    def check_alarm_status(self):
        # 음악이 끝났는데 활성화된 무한반복 알람이 있으면 다시 재생
        if not pygame.mixer.music.get_busy() and self.active_alarms:
            # 활성화된 알람 중 하나라도 '무한 반복'이면 다시 재생
            should_loop = False
            target_vol = 0.5

            for item_id in self.active_alarms:
                # 데이터 찾기
                item_data = next((item for item in self.items_data if item['id'] == item_id), None)
                if item_data:
                    if item_data['loop']:
                        should_loop = True
                        target_vol = item_data['volume'] / 100.0 # 루프되는 항목의 볼륨 사용

            if should_loop:
                pygame.mixer.music.set_volume(target_vol)
                pygame.mixer.music.play()
            else:
                # 1회 재생들만 있었으면 리스트 비우고 종료 (이미 소리는 멈춤)
                self.active_alarms.clear()

        self.root.after(500, self.check_alarm_status)

    def on_close(self):
        # 종료 시 스레드 정리
        for t in self.threads.values():
            t.stop()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AppLogic(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()