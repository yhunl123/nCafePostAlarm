import time
import threading
import tkinter as tk
from tkinter import ttk
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import pygame
import os
import sys

# ==========================================
# [사용자 설정] 아래 내용을 사용 환경에 맞게 수정하세요
# ==========================================

# 1. 알람으로 사용할 MP3 파일의 절대 경로
# ALARM_FILE_PATH = r""
# 현재 실행 파일(exe)이 있는 위치를 찾음
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

# 같은 폴더 내의 alarm.mp3 파일 지정
ALARM_FILE_PATH = os.path.join(application_path, "alarm.mp3")

# 2. 감시할 네이버 카페 '특정 게시판'의 URL
TARGET_BOARD_URL = "https://cafe.naver.com/f-e/cafes/31352147/menus/13"

# 3. 감시할 대상 닉네임 (옵션)
# - 특정 닉네임만 감시하려면: "닉네임 입력"
# - 게시판의 모든 새 글을 감시하려면: "" (빈 따옴표)
TARGET_NICKNAME = ""

# 4. 새로고침 주기 (초 단위)
CHECK_INTERVAL = 60

# ==========================================

class CafeMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("네이버 카페 알리미")
        self.root.geometry("400x300")
        self.root.resizable(False, False)

        # 상태 변수
        self.is_running = True
        self.is_loop_mode = True  # True: 무한반복, False: 1회재생
        self.last_article_id = 0
        self.alarm_active = False # 현재 알람이 '켜진' 상태인지 추적하는 변수

        # Pygame 오디오 초기화
        pygame.mixer.init()
        self.load_music()

        # UI 구성
        self.setup_ui()

        # 알람 상태 감시 루프 시작 (새로 추가됨)
        self.check_music_status()

        # 크롤링 모니터링 스레드 시작
        self.start_monitoring_thread()

    def load_music(self):
        if os.path.exists(ALARM_FILE_PATH):
            try:
                pygame.mixer.music.load(ALARM_FILE_PATH)
            except Exception as e:
                print(f"오디오 로드 실패: {e}")
        else:
            print(f"파일을 찾을 수 없습니다: {ALARM_FILE_PATH}")

    def setup_ui(self):
        # 상태바 배치
        self.status_label = tk.Label(self.root, text="초기화 중...", font=("맑은 고딕", 9), anchor="center", bg="#f0f0f0")
        self.status_label.pack(side="bottom", fill="x", pady=10)

        # 메인 프레임
        main_frame = tk.Frame(self.root, padx=20, pady=20)
        main_frame.pack(expand=True, fill="both", side="top")

        # 1. 반복 설정 버튼
        self.btn_loop = tk.Button(main_frame, text="알림 무한 반복", font=("맑은 고딕", 12, "bold"),
                                  command=self.toggle_loop_mode, width=20, height=2, borderwidth=2, relief="solid")
        self.btn_loop.pack(pady=(10, 20))

        # 2. 볼륨 조절
        vol_frame = tk.Frame(main_frame)
        vol_frame.pack(fill="x", pady=5)

        tk.Label(vol_frame, text="볼륨 : ", font=("맑은 고딕", 11, "bold")).pack(side="left")

        self.vol_scale = ttk.Scale(vol_frame, from_=0, to=100, orient="horizontal", command=self.set_volume)
        self.vol_scale.set(10)
        self.vol_scale.pack(side="left", fill="x", expand=True, padx=10)
        pygame.mixer.music.set_volume(0.1)

        # 3. 버튼 그룹
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=30)

        self.btn_test = tk.Button(btn_frame, text="알람 테스트", font=("맑은 고딕", 11, "bold"),
                                  command=self.test_alarm, width=12, height=2, borderwidth=2, relief="solid")
        self.btn_test.pack(side="left", padx=(0, 10))

        self.btn_stop = tk.Button(btn_frame, text="알람 끄기", font=("맑은 고딕", 11, "bold"), fg="red",
                                  command=self.stop_alarm, width=12, height=2, borderwidth=2, relief="solid")
        self.btn_stop.pack(side="right")

    def toggle_loop_mode(self):
        self.is_loop_mode = not self.is_loop_mode
        if self.is_loop_mode:
            self.btn_loop.config(text="알림 무한 반복")
        else:
            self.btn_loop.config(text="알림 1회 재생")

    def set_volume(self, val):
        volume = float(val) / 100
        pygame.mixer.music.set_volume(volume)

    def test_alarm(self):
        self.play_alarm(is_test=True)

    def stop_alarm(self):
        """알람 강제 종료"""
        pygame.mixer.music.stop()
        self.alarm_active = False # 알람 활성 상태 해제
        self.update_status("알람이 중지되었습니다.")

    def play_alarm(self, is_test=False):
        """알람 재생 시작"""
        # 이미 재생 중이면(busy) 무시
        if not pygame.mixer.music.get_busy():
            try:
                # 무조건 1회만 재생 (반복 여부는 check_music_status에서 결정)
                pygame.mixer.music.play(loops=0)
                self.alarm_active = True # 알람 활성 상태로 변경

                if not is_test:
                    target_msg = f"[{TARGET_NICKNAME}]" if TARGET_NICKNAME else "[새 글]"
                    self.update_status(f"!!! {target_msg} 감지됨 - 알람 울림 !!!")
            except Exception as e:
                self.update_status(f"재생 오류: {e}")

    def check_music_status(self):
        """
        0.1초마다 오디오 상태를 확인하여 수동으로 반복 재생을 처리하는 함수
        """
        if self.alarm_active:
            # 알람이 켜져 있어야 하는 상태인데, 소리가 멈췄다면(곡이 끝남)
            if not pygame.mixer.music.get_busy():
                if self.is_loop_mode:
                    # 반복 모드면 다시 재생
                    try:
                        pygame.mixer.music.play(loops=0)
                    except:
                        self.alarm_active = False
                else:
                    # 1회 재생 모드면 상태 종료
                    self.alarm_active = False

        # 100ms 뒤에 다시 실행 (재귀 호출)
        self.root.after(100, self.check_music_status)

    def update_status(self, text):
        self.root.after(0, lambda: self.status_label.config(text=text))

    def start_monitoring_thread(self):
        t = threading.Thread(target=self.monitor_logic)
        t.daemon = True
        t.start()

    def monitor_logic(self):
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        try:
            self.update_status("게시판 접속 중 (백그라운드)...")
            driver.get(TARGET_BOARD_URL)
            time.sleep(2)

            self.last_article_id = self.get_latest_post_id(driver)

            target_info = f"'{TARGET_NICKNAME}' 감시" if TARGET_NICKNAME else "전체 감시"
            if self.last_article_id > 0:
                self.update_status(f"모니터링 시작 ({target_info}) - 최신글: {self.last_article_id}")
            else:
                self.update_status("게시글을 인식할 수 없습니다. selector 확인 필요.")

            while self.is_running:
                time.sleep(CHECK_INTERVAL)

                try:
                    driver.refresh()
                    time.sleep(2)

                    if self.check_new_posts(driver):
                        self.play_alarm()

                except Exception as e:
                    print(f"Loop Error: {e}")

        except Exception as e:
            self.update_status(f"에러 발생: {e}")
            print(e)
        finally:
            driver.quit()

    def get_list_items(self, driver):
        try:
            driver.switch_to.frame("cafe_main")
        except:
            pass
        rows = driver.find_elements(By.CSS_SELECTOR, "div.article-board table tbody tr")
        return rows

    def get_latest_post_id(self, driver):
        rows = self.get_list_items(driver)
        for row in rows:
            try:
                num_element = row.find_element(By.CSS_SELECTOR, "td.type_articleNumber")
                num_text = num_element.text.strip()
                if num_text.isdigit():
                    return int(num_text)
            except NoSuchElementException:
                continue
            except Exception:
                continue
        return 0

    def check_new_posts(self, driver):
        rows = self.get_list_items(driver)
        found_new = False
        max_id_in_page = self.last_article_id

        for row in rows:
            try:
                try:
                    num_element = row.find_element(By.CSS_SELECTOR, "td.type_articleNumber")
                except NoSuchElementException:
                    continue

                num_text = num_element.text.strip()
                if not num_text.isdigit():
                    continue

                current_id = int(num_text)

                if current_id <= self.last_article_id:
                    break

                if current_id > max_id_in_page:
                    max_id_in_page = current_id

                try:
                    writer_element = row.find_element(By.CSS_SELECTOR, "td.td_name")
                    writer_text = writer_element.text.strip()
                except NoSuchElementException:
                    writer_text = ""

                is_target_match = False
                if not TARGET_NICKNAME:
                    is_target_match = True
                elif TARGET_NICKNAME in writer_text:
                    is_target_match = True

                if is_target_match:
                    found_new = True
                    self.update_status(f"새 글 발견! 번호:{current_id}, 작성자:{writer_text}")

            except Exception as e:
                continue

        if max_id_in_page > self.last_article_id:
            self.last_article_id = max_id_in_page

        return found_new

if __name__ == "__main__":
    root = tk.Tk()
    app = CafeMonitorApp(root)
    root.mainloop()