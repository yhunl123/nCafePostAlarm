import time
import threading
import tkinter as tk
from tkinter import ttk
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import pygame
import os

# ==========================================
# [사용자 설정] 아래 내용을 사용 환경에 맞게 수정하세요
# ==========================================

# 1. 알람으로 사용할 MP3 파일의 절대 경로
ALARM_FILE_PATH = r""

# 2. 감시할 네이버 카페 '특정 게시판'의 URL
# "https://cafe.naver.com/ArticleList.nhn?search.clubid=카페ID&search.menuid=게시판ID&search.boardtype=L"
TARGET_BOARD_URL = ""

# 3. 감시할 대상 닉네임 (옵션)
# - 특정 닉네임만 감시하려면: "닉네임 입력"
# - 게시판의 모든 새 글을 감시하려면: "" (빈 따옴표로 둠)
TARGET_NICKNAME = ""

# 4. 새로고침 주기 (초 단위)
CHECK_INTERVAL = 30

# ==========================================

class CafeMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("네이버 카페 알리미")
        self.root.geometry("400x250")
        self.root.resizable(False, False)

        # 상태 변수
        self.is_running = True
        self.is_loop_mode = True  # True: 무한반복, False: 1회재생
        self.last_article_id = 0  # 가장 최근 확인한 게시글 번호

        # Pygame 오디오 초기화
        pygame.mixer.init()
        self.load_music()

        # UI 구성
        self.setup_ui()

        # 모니터링 자동 시작
        self.start_monitoring_thread()

    def load_music(self):
        """음원 파일 로드"""
        if os.path.exists(ALARM_FILE_PATH):
            try:
                pygame.mixer.music.load(ALARM_FILE_PATH)
            except Exception as e:
                print(f"오디오 로드 실패: {e}")
        else:
            print(f"파일을 찾을 수 없습니다: {ALARM_FILE_PATH}")

    def setup_ui(self):
        # 전체를 감싸는 메인 프레임
        main_frame = tk.Frame(self.root, padx=20, pady=20)
        main_frame.pack(expand=True, fill="both")

        # 1. 상단: 반복 설정 버튼 (토글)
        self.btn_loop = tk.Button(main_frame, text="알림 무한 반복", font=("맑은 고딕", 12, "bold"),
                                  command=self.toggle_loop_mode, width=20, height=2, borderwidth=2, relief="solid")
        self.btn_loop.pack(pady=(0, 15))

        # 2. 중간: 볼륨 조절
        vol_frame = tk.Frame(main_frame)
        vol_frame.pack(fill="x", pady=5)

        tk.Label(vol_frame, text="볼륨 : ", font=("맑은 고딕", 11, "bold")).pack(side="left")

        self.vol_scale = ttk.Scale(vol_frame, from_=0, to=100, orient="horizontal", command=self.set_volume)
        self.vol_scale.set(70) # 기본 볼륨 70
        self.vol_scale.pack(side="left", fill="x", expand=True, padx=10)
        pygame.mixer.music.set_volume(0.7)

        # 3. 하단 버튼 그룹 (테스트, 끄기)
        btn_frame = tk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=20)

        # 알람 테스트 버튼
        self.btn_test = tk.Button(btn_frame, text="알람 테스트", font=("맑은 고딕", 11, "bold"),
                                  command=self.test_alarm, width=12, height=2, borderwidth=2, relief="solid")
        self.btn_test.pack(side="left", padx=(0, 10))

        # 알람 끄기 버튼
        self.btn_stop = tk.Button(btn_frame, text="알람 끄기", font=("맑은 고딕", 11, "bold"), fg="red",
                                  command=self.stop_alarm, width=12, height=2, borderwidth=2, relief="solid")
        self.btn_stop.pack(side="right")

        # 4. 최하단 상태 표시줄
        self.status_label = tk.Label(self.root, text="백그라운드 모니터링 시작 중...", font=("맑은 고딕", 9), anchor="center")
        self.status_label.pack(side="bottom", fill="x", pady=5)

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
        pygame.mixer.music.stop()
        self.update_status("알람이 중지되었습니다.")

    def play_alarm(self, is_test=False):
        if not pygame.mixer.music.get_busy():
            try:
                loops = -1 if self.is_loop_mode else 0
                pygame.mixer.music.play(loops=loops)
                if not is_test:
                    target_msg = f"[{TARGET_NICKNAME}]" if TARGET_NICKNAME else "[새 글]"
                    self.update_status(f"!!! {target_msg} 감지됨 - 알람 울림 !!!")
            except Exception as e:
                self.update_status(f"재생 오류: {e}")

    def update_status(self, text):
        self.status_label.config(text=text)

    def start_monitoring_thread(self):
        t = threading.Thread(target=self.monitor_logic)
        t.daemon = True
        t.start()

    def monitor_logic(self):
        # === 백그라운드(Headless) 설정 ===
        options = Options()
        options.add_argument("--headless") # 창 숨기기 활성화
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        # 봇 탐지 방지를 위한 User-Agent 설정
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")

        # 드라이버 매니저를 통해 자동 설치 및 실행
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        try:
            self.update_status("게시판 접속 중 (백그라운드)...")
            driver.get(TARGET_BOARD_URL)
            time.sleep(2)

            # 최초 기준점 잡기
            self.last_article_id = self.get_latest_post_id(driver)

            target_info = f"'{TARGET_NICKNAME}' 감시" if TARGET_NICKNAME else "전체 감시"
            if self.last_article_id > 0:
                self.update_status(f"모니터링 시작 ({target_info}) - 최신글: {self.last_article_id}")
            else:
                self.update_status("게시글을 찾을 수 없습니다. 설정 확인 필요.")

            while self.is_running:
                time.sleep(CHECK_INTERVAL)

                try:
                    driver.refresh()
                    time.sleep(2) # 로딩 대기

                    # 새 글 감지 로직 실행
                    new_post_found = self.check_new_posts(driver)

                    if new_post_found:
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
        rows = driver.find_elements(By.CSS_SELECTOR, "div.article-board > table > tbody > tr")
        return rows

    def get_latest_post_id(self, driver):
        rows = self.get_list_items(driver)
        for row in rows:
            try:
                num_text = row.find_element(By.CSS_SELECTOR, "td.td_article").text.strip()
                if num_text.isdigit():
                    return int(num_text)
            except:
                continue
        return 0

    def check_new_posts(self, driver):
        rows = self.get_list_items(driver)
        found_new = False
        max_id_in_page = self.last_article_id

        for row in rows:
            try:
                # 1. 글 번호 확인
                num_element = row.find_element(By.CSS_SELECTOR, "td.td_article")
                num_text = num_element.text.strip()

                if not num_text.isdigit(): # 공지사항 건너뛰기
                    continue

                current_id = int(num_text)

                # 이미 확인한 글 번호 이하라면 탐색 중단
                if current_id <= self.last_article_id:
                    break

                if current_id > max_id_in_page:
                    max_id_in_page = current_id

                # 2. 작성자 확인 (옵션 적용)
                writer_element = row.find_element(By.CSS_SELECTOR, "td.td_name")
                writer_text = writer_element.text.strip()

                # 조건: 닉네임 설정이 없거나 OR 닉네임이 일치하거나
                is_target_match = False
                if not TARGET_NICKNAME: # 설정값이 비어있으면 무조건 True
                    is_target_match = True
                elif TARGET_NICKNAME in writer_text: # 설정값이 있으면 일치 여부 확인
                    is_target_match = True

                if is_target_match:
                    found_new = True
                    self.update_status(f"새 글 발견! 번호:{current_id}, 작성자:{writer_text}")

            except Exception as e:
                continue

        # 상태 업데이트 (마지막 확인한 글 번호 갱신)
        if max_id_in_page > self.last_article_id:
            self.last_article_id = max_id_in_page
            if not found_new:
                # 새 글은 올라왔지만, 타겟 닉네임이 아니라서 알람은 안 울린 경우
                self.update_status(f"모니터링 중... (최신글 갱신: {self.last_article_id})")

        return found_new

if __name__ == "__main__":
    root = tk.Tk()
    app = CafeMonitorApp(root)
    root.mainloop()