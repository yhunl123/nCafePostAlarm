import tkinter as tk
from tkinter import ttk, messagebox
import json
import threading
import time
import os
import pygame
import uuid
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ==========================================
# [설정] 실행 파일/스크립트 위치 기준 경로 설정
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
# [개별 감시 스레드 클래스]
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
        self.driver = None
        self.last_article_id = 0
        self.daemon = True # 메인 종료 시 같이 종료되도록 설정하지만, 리소스 정리는 별도로 함

    def run(self):
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")

        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)

            self.driver.get(self.url)
            time.sleep(2)

            self.last_article_id = self.get_latest_post_id()
            self.callback_init(self.item_id, self.last_article_id)

            while self.is_running:
                # interval 동안 잠들기 (1초씩 쪼개서 종료 신호 확인)
                for _ in range(self.interval):
                    if not self.is_running: break
                    time.sleep(1)

                if not self.is_running: break

                try:
                    self.driver.refresh()
                    time.sleep(2)
                    self.check_new_posts()
                except Exception as e:
                    # 종료 과정에서 드라이버가 먼저 닫히면 에러가 날 수 있음 -> 무시
                    if self.is_running:
                        self.callback_error(self.item_id, str(e))

        except Exception as e:
            if self.is_running:
                self.callback_error(self.item_id, str(e))
        finally:
            # 스레드 내부에서의 안전 종료 (혹시 모를 상황 대비)
            self.close_driver_safe()

    def get_latest_post_id(self):
        try:
            self.driver.switch_to.frame("cafe_main")
        except: pass

        try:
            rows = self.driver.find_elements(By.CSS_SELECTOR, "div.article-board table tbody tr")
            for row in rows:
                try:
                    num_txt = row.find_element(By.CSS_SELECTOR, "td.type_articleNumber").text.strip()
                    if num_txt.isdigit():
                        return int(num_txt)
                except: continue
        except: pass
        return 0

    def check_new_posts(self):
        try:
            self.driver.switch_to.frame("cafe_main")
        except: pass

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

                writer_text = ""
                try:
                    writer_text = row.find_element(By.CSS_SELECTOR, "td.td_name").text.strip()
                except: pass

                is_match = False
                if not self.nickname_filter: is_match = True
                elif self.nickname_filter in writer_text: is_match = True

                if is_match:
                    found_new = True
                    self.callback_found(self.item_id, current_id, writer_text)
            except: continue

        if max_id_in_page > self.last_article_id:
            self.last_article_id = max_id_in_page

    # [수정 8차] 외부에서 강제로 드라이버를 닫는 메서드
    def stop_and_quit_driver(self):
        self.is_running = False
        self.close_driver_safe()

    def close_driver_safe(self):
        if self.driver:
            try:
                # quit()은 브라우저 창과 해당 ChromeDriver 프로세스를 종료함
                self.driver.quit()
            except:
                pass
            finally:
                self.driver = None

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

        # 1. 항목 이름
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

        # 3. 우측 컨트롤
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
        self.root.title("네이버 카페 멀티 알리미")
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

        btn_add = tk.Button(top_frame, text="입력 버튼", command=self.add_new_item, bg="#4a90e2", fg="white", font=("맑은 고딕", 9, "bold"))
        btn_add.pack(side="left")

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

    def add_new_item(self):
        url = self.entry_url.get().strip()
        if not url:
            messagebox.showwarning("입력 오류", "URL을 입력해주세요.")
            return

        if "cafe.naver.com" not in url or not url.startswith("http"):
            messagebox.showerror("입력 오류", "유효하지 않은 링크입니다.\n네이버 카페 게시판 주소(cafe.naver.com)를 입력해주세요.")
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
            # 삭제 시에도 안전 종료
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
            self.widgets[item_id].set_status(f"감시중... (최신글: {last_id})", is_alarm=False)

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

    def stop_alarm(self, item_id):
        if item_id in self.active_alarms:
            self.active_alarms.remove(item_id)

        if item_id in self.widgets:
            current_last_id = 0
            if item_id in self.threads:
                current_last_id = self.threads[item_id].last_article_id

            self.widgets[item_id].set_status(f"감시중... (최신글: {current_last_id})", is_alarm=False)

        if not self.active_alarms:
            pygame.mixer.music.stop()

    def check_alarm_status(self):
        if not pygame.mixer.music.get_busy() and self.active_alarms:
            should_loop = False
            target_vol = 0.5

            for item_id in self.active_alarms:
                item_data = next((item for item in self.items_data if item['id'] == item_id), None)
                if item_data:
                    if item_data['loop']:
                        should_loop = True
                        target_vol = item_data['volume'] / 100.0

            if should_loop:
                pygame.mixer.music.set_volume(target_vol)
                pygame.mixer.music.play()
            else:
                self.active_alarms.clear()

        self.root.after(500, self.check_alarm_status)

    # [수정 8차] 종료 시 로직 강화
    def on_close(self):
        # 1. 종료 메시지 (짧게 표시하고 싶다면 아래 주석 해제)
        # self.root.title("리소스 정리 중...")

        # 2. 모든 활성 스레드에 대해 '드라이버 강제 종료' 실행
        # 리스트로 변환하여 순회 (도중에 dict가 변경되는 것 방지)
        active_threads = list(self.threads.values())

        for t in active_threads:
            # 이 함수는 해당 스레드가 관리하는 driver.quit()을 직접 호출함
            # 이 과정은 순차적으로 실행되며, 모든 크롬이 꺼질 때까지 메인 윈도우가 잠시 멈출 수 있음
            t.stop_and_quit_driver()

        # 3. 모든 정리가 끝난 후 윈도우 파괴 및 프로그램 종료
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AppLogic(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()