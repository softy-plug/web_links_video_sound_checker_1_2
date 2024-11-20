# Install required packages via pip if not already installed
os.system("pip install selenium webdriver-manager python-ffmpeg")
os.system("pip3 install ffprobe")

input("Нажмите Enter для запуска программы")

import os
import time
import subprocess
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

# Function to read URLs from a text file
def read_links_from_file(file_path):
    with open(file_path, 'r') as file:
        links = file.readlines()
    return [link.strip() for link in links]

# Initialize the WebDriver (Chrome in this case)
def init_browser():
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
    service = ChromeService(executable_path=ChromeDriverManager().install())
    browser = webdriver.Chrome(service=service, options=options)
    return browser

# Function to check if a link is a valid .mp4 video file
def is_video_link(url):
    return url.lower().endswith('.mp4')

# Function to get the size of the video file and its resolution
def get_file_size_and_resolution(url):
    command = ['ffprobe', '-v', 'error', '-show_entries', 'format=size', 
               '-show_entries', 'stream=width,height', '-of', 
               'default=noprint_wrappers=1:nokey=1', url]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if result.returncode == 0:
        output = result.stdout.strip().split('\n')
        if len(output) >= 3:
            file_size = int(output[0])  # Size in bytes
            width = int(output[1])
            height = int(output[2])
            resolution = (width, height)
            return file_size, resolution
    return None, None  # Return None if there's an error

# Function to check if the video loads successfully
def check_video_link(browser, url):
    try:
        browser.get(url)
        time.sleep(2)  # Wait for the page to load
        
        # Check if the video element is present
        video_elements = browser.find_elements(By.TAG_NAME, 'video')
        return bool(video_elements)  # Returns True if video element found
    except Exception as e:
        log_error(f"Error accessing {url}: {e}")
    return False  # Catch-all for other issues

# Function to extract audio level using FFmpeg
def get_audio_level(segment_file):
    command = [
        'ffmpeg', '-i', segment_file, 
        '-af', 'volumedetect', 
        '-f', 'null', '/dev/null'
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    output = result.stderr
    return extract_volume_level(output)

# Function to extract volume level from FFmpeg output
def extract_volume_level(output):
    for line in output.split('\n'):
        if 'max_volume' in line:
            return line.split(':')[-1].strip()
    return "N/A"  # If volume level can't be determined

# Function to extract video segments
def extract_segments(url):
    segments = []
    base_name = url.split('/')[-1].split('.')[0]  # Extract base name
    # Define segment timings in seconds
    segment_timings = [0, 30, 60]  # Start extraction from 0, 30 seconds, and 1 minute

    for start in segment_timings:
        segment_file = f"{base_name}_segment_{start}.mp4"
        command = [
            'ffmpeg', '-ss', str(start), '-i', url,
            '-t', '10', '-c', 'copy', segment_file, '-y'
        ]
        subprocess.run(command)
        segments.append(segment_file)
    
    return segments

# Function to check for static frames in a video segment
def check_static_frames(segment_file):
    static_frames_count = 0  
    command = [
        'ffmpeg', '-i', segment_file, 
        '-vf', 'select=gt(scene\,0.4)', '-vsync', 'vfr', 
        'output_%03d.png'
    ]
    subprocess.run(command)

    # Auto-delete .png files after analysis
    frame_images = [f"output_{i:03d}.png" for i in range(1, 4)]
    
    for frame in frame_images:
        if os.path.exists(frame):
            os.remove(frame)
    return static_frames_count

# Function to log errors and warnings
def log_error(message):
    with open('error_log.txt', 'a') as error_file:
        error_file.write(message + '\n')

# Main function to check all links from the file
def main():
    links = read_links_from_file('links.txt')
    browser = init_browser()
    results = {}

    for link in links:
        if is_video_link(link):
            success = check_video_link(browser, link)
            results[link] = {'success': success, 'audio_levels': [], 'segment_files': [], 'warnings': [], 'static_frame_errors': 0}

            if success:
                # Get the size of the video file and resolution
                file_size, resolution = get_file_size_and_resolution(link)  
                
                if file_size is not None and resolution is not None:
                    width, height = resolution
                    size_mb = file_size / (1024 * 1024)  # Convert bytes to MB
                    
                    # Check video duration condition
                    if size_mb < 20 * 1024:  # Assuming 20 minutes in MB
                        results[link]['warnings'].append("WARNING: Видео меньше 20 минут.")

                    # Check file size based on resolution
                    if height == 720:
                        if size_mb > 1024 or size_mb < 40:
                            results[link]['warnings'].append("WARNING: Файл больше 1 ГБ или меньше 40 МБ.")
                    elif height == 1080:
                        if size_mb > 2048 or size_mb < 40:
                            results[link]['warnings'].append("WARNING: Файл больше 2 ГБ или меньше 40 МБ.")

                    # Wait for 5 seconds to view the video
                    print(f"Loading video: {link}")
                    time.sleep(5)

                    # Extract segments and check audio levels
                    segment_files = extract_segments(link)
                    results[link]['segment_files'] = segment_files

                    static_frames_total = 0
                    for segment in segment_files:
                        audio_level = get_audio_level(segment)
                        results[link]['audio_levels'].append(audio_level)
                        print(f"Audio level for {segment}: {audio_level}")

                        if audio_level == '-91.0 dB':
                            log_error(f"WARNING: Уровень звука в сегменте {segment} равен -91.0 dB.")

                        static_frames = check_static_frames(segment)
                        static_frames_total += static_frames

                    if static_frames_total >= 3:
                        results[link]['static_frame_errors'] += 1
                        log_error(f"ERROR: У видео {link} найдено 5 секунд статических кадров во всех сегментах.")
                
                    # Delete segment files after processing
                    for segment in segment_files:
                        if os.path.exists(segment):
                            os.remove(segment)

                else:
                    log_error(f"ERROR: Не удалось получить размер или разрешение для {link}")

            print(f"URL: {link} - {'Success' if success else 'Failed to load video'}")

        else:
            results[link] = {'success': False, 'audio_levels': [], 'segment_files': [], 'warnings': ['Invalid link']}
            print(f"URL: {link} - Invalid video link (not .mp4)")

    browser.quit()

    # Write results to a file
    with open('results.txt', 'w') as result_file:
        for link, status in results.items():
            result_file.write(f"{link} - {'Success' if status['success'] else 'Failed to load video or invalid link'}\n")
            result_file.write(f"Audio Levels: {', '.join(status['audio_levels'])}\n")
            result_file.write(f"Segments: {', '.join(status['segment_files'])}\n")
            if status['static_frame_errors'] > 0:
                result_file.write(f"ERROR: Статические кадры обнаружены в сегментах.\n")
            result_file.write(f"WARNINGS: {', '.join(status['warnings'])}\n")

if __name__ == "__main__":
    main()

input("Проверка ссылок завершена. Нажмите Enter для закрытия окна")

# softy_plug