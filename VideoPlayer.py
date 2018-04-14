import os
import glob
import time
import datetime
import threading
import tkinter as tk
from queue import Queue, Empty
import code

import numpy as np
import pyaudio
from PIL import Image, ImageTk

import config
from Video import Video


class VideoPlayer(tk.Frame):
    PLAY = 0
    PAUSE = 1

    def __init__(self, master, video_obj):
        super().__init__(master)
        self.pack()

        # self.root = tk.Tk()
        # self.root.wm_title("Video Query")
        # self.root.overrideredirect(1)

        self.video_obj = video_obj

        self.pyaudio_inst = pyaudio.PyAudio()
        self.audio_stream = self.pyaudio_inst.open(
            format=self.pyaudio_inst.get_format_from_width(
                self.video_obj.audio_width),
            channels=self.video_obj.audio_channels,
            rate=self.video_obj.audio_rate,
            frames_per_buffer=video_obj.audioframes_per_videoframe,
            output=True,
            stream_callback=self.play_audio_frame
        )

        self.init_frame = np.zeros(
            (
                config.FRAME_DIM[1],
                config.FRAME_DIM[0],
                config.FRAME_DIM[2]
            ),
            dtype='uint8'
        )

        init_frame = ImageTk.PhotoImage(
            Image.fromarray(
                self.init_frame
            )
        )

        quit_btn = tk.Button(
            self, text='QUIT',
            command=self.onClose
        )

        self.panel = tk.Label(self, image=init_frame)
        self.panel.image = init_frame
        self.panel.pack(side='top')

        self.play_pause_btn = tk.Button(
            self, text=u'\u23f8', command=self.play_pause
        )

        # pause_btn = tk.Button(
        #     self.root, text='PAUSE', command=self.pause
        # )
        # pause_btn.pack(side='right')

        stop_btn = tk.Button(
            self, text='\u23f9', command=self.stop
        )

        # seek_btn = tk.Button(
        #     self.root, text='RESET',
        #     command=self.seek
        # )
        self.seek_bar = tk.Scale(
            self, from_=0, to=self.video_obj.num_video_frames,
            orient=tk.HORIZONTAL, command=self.seek, length=200,
            showvalue=0
        )

        self.time_label = tk.Label(self, text="--:--")

        quit_btn.pack(side='top')
        self.play_pause_btn.pack(side='left')
        stop_btn.pack(side='left')
        self.seek_bar.pack(side='left')
        self.time_label.pack(side='left')

        self.videoBuffer = Queue(maxsize=2)
        self.audioBuffer = Queue(maxsize=2)

        self.bufferingThread = threading.Thread(target=self.buffer_frame_data)
        self.renderingThread = threading.Thread(target=self.play_video_frame)

        self.stop_buffering = threading.Event()
        self.stop_rendering = threading.Event()

        self.frame_ptr = 0
        self.state = self.PLAY

        self.delay = self.video_obj.frame_delay

        self.bufferingThread.start()
        self.renderingThread.start()

    def buffer_frame_data(self):
        while not self.stop_buffering.is_set():
            if self.state == self.PLAY:
                vid_frame = self.video_obj.get_video_frame(self.frame_ptr)
                aud_frame = self.video_obj.get_audio_frame(self.frame_ptr)
                self.videoBuffer.put(vid_frame)
                self.audioBuffer.put(aud_frame)

                # Change to mod to loop video
                self.frame_ptr = self.frame_ptr + 1
                if not self.stop_buffering.is_set():
                    self.seek_bar.set(self.frame_ptr)
                    # time_str = str(datetime.timedelta(
                    #     seconds=self.delay * self.frame_ptr))
                    time_str = time.strftime(
                        "%M:%S", time.gmtime(self.delay * self.frame_ptr))
                    self.time_label.config(text=time_str)
                if self.frame_ptr == self.video_obj.num_video_frames:
                    self.state = self.PAUSE
        print('Stopping buffering thread')

    def play_video_frame(self):
        tic = time.time()
        while not self.stop_rendering.is_set():
            if self.state == self.PAUSE:
                pass
            else:
                # Read queue and render
                try:
                    frame = self.videoBuffer.get(timeout=0.1)
                    # print('rendering to screen')
                    self.draw_video_frame(frame)
                    # print('rendered')
                except Empty:
                    pass
                toc = time.time()
                delay = max(0, self.delay - (toc - tic))
                time.sleep(delay)
                tic = time.time()
                # stop_flag = self.stop_rendering.wait(delay)
                # print(delay)
        print('stopping rendering')

    def draw_video_frame(self, frame):
        if not self.stop_rendering.is_set():
            panel_frame = ImageTk.PhotoImage(
                Image.fromarray(frame)
            )
            self.panel.configure(image=panel_frame)
            self.panel.image = panel_frame

    def play_audio_frame(self, in_data, frame_count, time_info, status):
        try:
            if self.state == self.PAUSE:
                data = bytes(
                    frame_count * self.video_obj.audio_channels * self.video_obj.audio_width
                )
                return (data, pyaudio.paContinue)
            try:
                data = self.audioBuffer.get(timeout=0.1)
            except Empty:
                data = bytes(
                    frame_count * self.video_obj.audio_channels * self.video_obj.audio_width
                )
            return (data, pyaudio.paContinue)
        except:
            data = bytes(1)
            print('PyAudio buffer underflow. Stream aborted')
            return (data, pyaudio.paAbort)

    def play_pause(self):
        if self.state == self.PLAY:
            self.play_pause_btn.config(text='\u25b6')
            self.state = self.PAUSE
            return
        if self.frame_ptr < self.video_obj.num_video_frames:
            self.play_pause_btn.config(text='\u23f8')
            self.state = self.PLAY

    def stop(self):
        if self.state == self.PLAY:
            self.state = self.PAUSE
        self.frame_ptr = 0
        self.seek_bar.set(0)
        self.time_label.config(text="--:--")
        self.play_pause_btn.config(text='\u25b6')

        self.draw_video_frame(self.init_frame)

    def seek(self, value):
        self.frame_ptr = int(value)

    def onClose(self):
        self.state = self.PAUSE
        self.stop_buffering.set()
        while not self.videoBuffer.empty():
            self.videoBuffer.get()
        while not self.audioBuffer.empty():
            self.audioBuffer.get()
        print('Joining buffering thread')
        self.bufferingThread.join()
        print('Buffer thread complete')

        self.stop_rendering.set()
        print('Joining rendering thread')
        self.renderingThread.join()
        print('Render thread complete')
        root.quit()
        # self.master.destroy()


if __name__ == '__main__':
    folders = [x[0]
               for x in os.walk('D:\\Scripts\\CS576\\Final_project\\database\\')][1:]
    print('='*80)
    print('Video list')
    print('-'*80)
    print('\n'.join(['%d. %s' % (i+1, f) for (i, f) in enumerate(folders)]))
    print('='*80)

    choice = -1
    while choice not in range(1, len(folders)+1):
        choice = int(input('Select folder:'))

    selected_folder = folders[choice-1]
    print(selected_folder)

    vid_path = selected_folder
    aud_path = glob.glob(os.path.join(selected_folder, '*.wav'))[0]
    v = Video(vid_path, aud_path)
    root = tk.Tk()
    root.wm_title("Video Query")

    player = VideoPlayer(root, v)
    root.wm_protocol("WM_DELETE_WINDOW", player.onClose)
    try:
        root.mainloop()
    except:
        pass
    root.destroy()
    # onClose()
    # code.interact()