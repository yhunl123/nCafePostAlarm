import time
import threading
import tkinter as tk
from tkinter import ttk
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import pygame
import os

# ==========================================
# [사용자 설정] 아래 내용을 사용 환경에 맞게 수정하세요
# ==========================================

# 1. 알람으로 사용할 MP3 파일의 절대 경로 (경로 구분자는 \\ 또는 / 사용)
# 예시: r"C:\Users\MyName\Music\alarm.mp3"
ALARM_FILE_PATH = r"C:\path\to\your\file.mp3"

# 2. 감시할 네이버 카페 '특정 게시판'의 URL (전체글보기 또는 특정 게시판)
# 주의: 멤버 검색 결과 URL이 아닌, 게시판 목록이 나오는 URL이어야 합니다.
TARGET_BOARD_URL = "https://cafe.naver.com/ArticleList.nhn?search.clubid=카페ID&search.menuid=게시판ID&search.boardtype=L"

# 3. 감시할 대상 닉네임 (정확하게 입력)
TARGET_NICKNAME = "닉네임"

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

        # 알람 끄기 버튼 (빨간 테두리 느낌)
        self.btn_stop = tk.Button(btn_frame, text="알람 끄기", font=("맑은 고딕", 11, "bold"), fg="red",
                                  command=self.stop_alarm, width=12, height=2, borderwidth=2, relief="solid")
        self.btn_stop.pack(side="right")

        # 4. 최하단 상태 표시줄
        self.status_label = tk.Label(self.root, text="모니터링 초기화 중...", font=("맑은 고딕", 9), anchor="center")
        self.status_label.pack(side="bottom", fill="x", pady=5)

    def toggle_loop_mode(self):
        """반복 모드 토글"""
        self.is_loop_mode = not self.is_loop_mode
        if self.is_loop_mode:
            self.btn_loop.config(text="알림 무한 반복")
        else:
            self.btn_loop.config(text="알림 1회 재생")

    def set_volume(self, val):
        """볼륨 조절 (0.0 ~ 1.0)"""
        volume = float(val) / 100
        pygame.mixer.music.set_volume(volume)

    def test_alarm(self):
        """알람 테스트 재생"""
        self.play_alarm(is_test=True)

    def stop_alarm(self):
        """알람 중지"""
        pygame.mixer.music.stop()
        self.update_status("알람이 중지되었습니다.")

    def play_alarm(self, is_test=False):
        """알람 재생 로직"""
        if not pygame.mixer.music.get_busy(): # 이미 재생 중이면 무시
            try:
                # 무한 반복(-1) 또는 1회(0)
                loops = -1 if self.is_loop_mode else 0
                pygame.mixer.music.play(loops=loops)

                if not is_test:
                    self.update_status("!!! 새 글 감지됨 - 알람 울림 !!!")
            except Exception as e:
                self.update_status(f"재생 오류: {e}")

    def update_status(self, text):
        """하단 상태바 텍스트 업데이트 (Thread-safe)"""
        self.status_label.config(text=text)

    def start_monitoring_thread(self):
        """별도 스레드에서 모니터링 실행"""
        t = threading.Thread(target=self.monitor_logic)
        t.daemon = True
        t.start()

    def monitor_logic(self):
        """실제 크롤링 로직"""
        # Headless 모드 설정 (창 숨기기)
        options = Options()
        # options.add_argument("--headless") # 테스트 시에는 주석 처리하여 브라우저 확인 추천
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")

        driver = webdriver.Chrome(options=options)

        try:
            self.update_status("게시판 접속 중...")
            driver.get(TARGET_BOARD_URL)
            time.sleep(2)

            # 최초 기준점 잡기
            self.last_article_id = self.get_latest_post_id(driver)
            if self.last_article_id > 0:
                self.update_status(f"모니터링 시작 (현재 최신글: {self.last_article_id})")
            else:
                self.update_status("게시글을 찾을 수 없습니다. 설정 확인 필요.")

            while self.is_running:
                time.sleep(CHECK_INTERVAL)

                # 새로고침
                driver.refresh()
                time.sleep(2) # 로딩 대기

                latest_id = self.get_latest_post_id(driver)

                # 새로운 글이 있고(> last_id) + 그 글이 타겟 유저의 글일 때
                # 주의: get_latest_post_id 함수 내부에서 타겟 유저 검증까지 수행하여
                # 타겟 유저의 '가장 최신 글 번호'를 가져오는 방식이 안전함

                # 로직 수정: 리스트를 훑어서 "내 기준글(last_id)보다 큰 번호" 중 "타겟 유저"가 쓴 글이 있는지 확인
                new_post_found = self.check_new_posts(driver)

                if new_post_found:
                    self.play_alarm()
                    # 기준 업데이트는 check_new_posts 내부에서 처리하거나 여기서 처리

        except Exception as e:
            self.update_status(f"에러 발생: {e}")
            print(e)
        finally:
            driver.quit()

    def get_list_items(self, driver):
        """게시글 리스트 엘리먼트 반환 (iframe 전환 처리)"""
        try:
            driver.switch_to.frame("cafe_main")
        except:
            pass

        # 게시판 리스트의 행(tr)들을 가져옴
        # 선택자는 네이버 카페 스킨마다 다를 수 있으나, 보통 아래 구조를 따름
        rows = driver.find_elements(By.CSS_SELECTOR, "div.article-board > table > tbody > tr")
        return rows

    def get_latest_post_id(self, driver):
        """
        초기 실행 시, 공지사항을 제외한 가장 최신 일반글의 ID를 반환
        """
        rows = self.get_list_items(driver)
        for row in rows:
            try:
                # 글 번호 추출 (첫번째 td)
                num_text = row.find_element(By.CSS_SELECTOR, "td.td_article").text.strip()

                # '공지', '필독' 등이 아닌 숫자인 경우만 리턴
                if num_text.isdigit():
                    return int(num_text)
            except:
                continue
        return 0

    def check_new_posts(self, driver):
        """
        리스트를 순회하며 last_article_id보다 큰 번호의 글 중
        Target Nickname이 작성한 글이 있는지 확인
        """
        rows = self.get_list_items(driver)
        found_new = False
        max_id_in_page = self.last_article_id

        for row in rows:
            try:
                # 1. 글 번호 확인
                num_element = row.find_element(By.CSS_SELECTOR, "td.td_article")
                num_text = num_element.text.strip()

                # 공지사항(숫자가 아님) 건너뛰기
                if not num_text.isdigit():
                    continue

                current_id = int(num_text)

                # 이미 확인한 글 번호 이하라면 더 볼 필요 없음 (내림차순 정렬이므로)
                if current_id <= self.last_article_id:
                    break

                # 현재 페이지에서 가장 큰 ID 갱신 (다음 비교를 위해)
                if current_id > max_id_in_page:
                    max_id_in_page = current_id

                # 2. 작성자 확인
                # 작성자 컬럼 (td_name) 내부의 텍스트 추출
                writer_element = row.find_element(By.CSS_SELECTOR, "td.td_name")
                writer_text = writer_element.text.strip()

                # 닉네임이 포함되어 있는지 확인 (정확도 높이기 위해 in 대신 == 권장하지만, 공백 등 고려 필요)
                if TARGET_NICKNAME in writer_text:
                    found_new = True
                    self.update_status(f"새 글 발견! 글번호: {current_id}, 작성자: {writer_text}")
                    # 여기서 break 하지 않는 이유는, 혹시 새 글이 여러 개일 경우 모두 확인하진 않아도 알람은 한 번만 울리면 되기 때문
                    # 다만 최신 ID 갱신은 루프 밖에서 일괄 처리

            except Exception as e:
                print(f"Row parsing error: {e}")
                continue

        # 상태 업데이트
        if max_id_in_page > self.last_article_id:
            self.last_article_id = max_id_in_page
            if not found_new:
                self.update_status(f"모니터링 중... (최신글: {self.last_article_id})")

        return found_new

if __name__ == "__main__":
    root = tk.Tk()
    app = CafeMonitorApp(root)
    root.mainloop()