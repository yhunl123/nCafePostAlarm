import time
import threading
import tkinter as tk
from tkinter import filedialog
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import pygame

# === 설정 부분 ===
CAFE_URL = "감시할_멤버의_검색결과_URL_입력" # 예: 특정 멤버 작성글 검색 결과 URL
CHECK_INTERVAL = 30  # 감시 주기 (초)

class CafeMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("네이버 카페 새 글 알리미")
        self.root.geometry("400x300")

        # 상태 변수
        self.is_running = False
        self.alarm_file = None
        self.is_loop = tk.BooleanVar() # 반복 재생 여부
        self.last_article_id = None

        # Pygame 오디오 초기화
        pygame.mixer.init()

        # GUI 구성
        self.setup_ui()

    def setup_ui(self):
        # 1. 파일 선택
        tk.Label(self.root, text="1. 알람 파일 선택 (mp3)").pack(pady=5)
        self.lbl_file = tk.Label(self.root, text="선택된 파일 없음", fg="gray")
        self.lbl_file.pack()
        tk.Button(self.root, text="파일 찾기", command=self.select_file).pack(pady=5)

        # 2. 반복 설정 (토글)
        tk.Checkbutton(self.root, text="알람 무한 반복 (체크 해제시 1회)", variable=self.is_loop).pack(pady=10)

        # 3. 알람 끄기 버튼
        self.btn_stop = tk.Button(self.root, text="알람 끄기 (STOP)", command=self.stop_alarm, bg="red", fg="white", state="disabled")
        self.btn_stop.pack(pady=10, fill='x', padx=20)

        # 4. 모니터링 시작 버튼
        self.btn_start = tk.Button(self.root, text="모니터링 시작", command=self.start_monitoring, bg="green", fg="white")
        self.btn_start.pack(pady=10, fill='x', padx=20)

        # 로그창
        self.txt_log = tk.Text(self.root, height=5)
        self.txt_log.pack(pady=5, padx=10)

    def log(self, msg):
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)

    def select_file(self):
        file = filedialog.askopenfilename(filetypes=[("Audio Files", "*.mp3 *.wav *.ogg")])
        if file:
            self.alarm_file = file
            self.lbl_file.config(text=file.split("/")[-1])
            self.log(f"파일 선택됨: {file}")

    def stop_alarm(self):
        pygame.mixer.music.stop()
        self.btn_stop.config(state="disabled")
        self.log("알람을 껐습니다.")

    def play_alarm(self):
        if not self.alarm_file:
            return

        try:
            pygame.mixer.music.load(self.alarm_file)
            # loop: -1은 무한반복, 0은 1회 재생
            loop_count = -1 if self.is_loop.get() else 0
            pygame.mixer.music.play(loops=loop_count)
            self.btn_stop.config(state="normal") # 끄기 버튼 활성화
        except Exception as e:
            self.log(f"재생 오류: {e}")

    def start_monitoring(self):
        if not self.alarm_file:
            self.log("먼저 알람 파일을 선택해주세요.")
            return

        self.is_running = True
        self.btn_start.config(state="disabled", text="모니터링 중...")

        # 별도 스레드에서 감시 시작 (GUI 멈춤 방지)
        t = threading.Thread(target=self.monitor_logic)
        t.daemon = True
        t.start()

    def monitor_logic(self):
        # Selenium 설정 (Headless 모드 권장)
        options = Options()
        options.add_argument("--headless") # 창 안띄우기
        driver = webdriver.Chrome(options=options)

        self.log("브라우저 초기화 완료...")

        try:
            # 최초 접속하여 기준점 잡기
            driver.get(CAFE_URL)
            time.sleep(2)

            # 네이버 카페는 iframe 내부에 본문이 있는 경우가 많음
            # 상황에 따라 switch_to.frame("cafe_main") 필요할 수 있음
            try:
                driver.switch_to.frame("cafe_main")
            except:
                pass

            # 게시글 리스트 파싱 (CSS Selector는 실제 카페 스킨에 따라 다름. 개발자 도구로 확인 필요)
            # 예: 게시글 ID를 추출
            recent_posts = driver.find_elements(By.CSS_SELECTOR, "div.inner_list > a.article")
            if recent_posts:
                # href 속성에서 articleid 추출 등을 수행
                self.last_article_id = recent_posts[0].text # 혹은 href 등의 고유값
                self.log(f"현재 최신글 기준: {self.last_article_id}")

            while self.is_running:
                time.sleep(CHECK_INTERVAL)
                driver.refresh()
                time.sleep(2)

                try:
                    driver.switch_to.frame("cafe_main")
                except:
                    pass

                new_posts = driver.find_elements(By.CSS_SELECTOR, "div.inner_list > a.article")
                if new_posts:
                    current_top_post = new_posts[0].text # 고유값 비교

                    if current_top_post != self.last_article_id:
                        self.log(f"새 글 감지됨! : {current_top_post}")
                        self.last_article_id = current_top_post

                        # GUI 스레드 쪽으로 알람 요청은 직접 호출해도 됨 (Pygame은 Thread safe한 편)
                        self.play_alarm()
        except Exception as e:
            self.log(f"에러 발생: {e}")
        finally:
            driver.quit()

if __name__ == "__main__":
    root = tk.Tk()
    app = CafeMonitorApp(root)
    root.mainloop()