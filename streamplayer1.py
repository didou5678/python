# -*- coding: UTF-8 -*-
import sys
import time
import threading
import queue
import subprocess
from typing import TypeVar,Union,Generic
import pyaudio
import os
import signal




# 限制精确到 3.7.3（最严格）
if sys.version_info < (3, 9):
    print(f"错误：需要 Python 3.9 及以上，当前版本: {sys.version}")
    sys.exit(1)

#手动设置该值 不为0 开启
_MYDEBUG=1
def debug_print(*args,**kwargs):
  if _MYDEBUG:
    print(*args,**kwargs)



if sys.platform.startswith("linux"):
    import pasimple
else:
    import pyaudio




"""
调用演示 
example 1 :
 #s=streamplayer[pasimple.PaSimple]()
 s=streamplayer[pyaudio.PyAudio]()
 s.play(input='http://127.0.0.1:18080/stream',retry=3,ffvol=50)
 
example 2:
 s=streamplayer[pasimple.PaSimple]()
 s.play('http://127.0.0.1:18080/stream',block=False)
 time.sleep(60)
 s.stop()
'''

example 2 : 播放30s后退出    
    s=streamplayer_pulse()
    s.play('http://127.0.0.1:18080/stream',block=False)
    a=time.time()
    while True:
        if (time.time()-a) >= 30:
        s.stop()
        break
        time.sleep(1)
        s.is_playing()
"""

_IS_LINUX = sys.platform.startswith("linux")

if _IS_LINUX:
  import ctypes
  #libc = ctypes.CDLL("libc.so.6")
  libc = ctypes.CDLL("libpthread.so.0")


T=TypeVar("T",bound=Union[pasimple.PaSimple,pyaudio.PyAudio])
class streamplayer(Generic[T]):
    
    def __thd_pcm_write(self):
        startime=int(time.time())
        while True:
            pcm=b''
            with self.__lock:
              if self.__flags[0]==1: return
            
            try:
              pcm=self.__que.get(True,self.__flags[1])
            except queue.Empty:
              #debug_print(f"{threading.current_thread().name}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S:%f')} play queue is empty")
              pcm=b''
              if (int(time.time()) - startime) >= self.__flags[2]:
                debug_print(f"{threading.current_thread().name}: recv timeout. exit.")
              
                self.__flags[0]=0  #使  __thd_pipe_read 尝试退出
                #关闭 ffmpeg stdout pipe 尝试使__thd_pipe_read 不阻塞
                os.close(self.__proc_ffmpeg.stdout.fileno())
                #退出ffmpeg
                self.__kill_ffmpeg() 
                return #退出自身
            except Exception as e:
              debug_print(f"{e}")
              pass 

            if pcm != b'' and pcm is not None:
                self.__stream.write(pcm) #pulse非阻塞式 pyaudio阻塞式
                startime=int(time.time())


    def __thd_pipe_read(self):
       self.__pthd_t_readpipe=libc.pthread_self()
       while True:
         with self.__lock:
            if self.__flags[0] == 1 : return
         if self.__proc_ffmpeg is not None and self.__proc_ffmpeg.poll() is None:
            self.__que.put(self.__proc_ffmpeg.stdout.read(self.__pipelen))  
         else:
            debug_print(f"{threading.current_thread().name}: no pipe read,thread exit.")
            return
         

    __Ttypelist: type[T] = None
    
    def __class_getitem__(cls,item):
       cls.__Ttypelist=item
       return cls

    def __createT(self):
       if self.__curtype == pyaudio.PyAudio:
          debug_print("Generics Type: pyaudio.PyAudio")
          self.__audio_obj=pyaudio.PyAudio()
          self.__stream=self.__audio_obj.open(
            format=pyaudio.paInt16,
            channels=2,
            rate=44100,
            output=True)
  
       elif self.__curtype == pasimple.PaSimple:
          debug_print("Generics Type: pasimple.PaSimple")
          self.__audio_obj=pasimple.PaSimple(
            direction=pasimple.PA_STREAM_PLAYBACK,
            format= pasimple.PA_SAMPLE_S16LE,
            channels=2,
            rate=44100,
            app_name=self._app_name,
            server_name=self.__pulseserver,
            device_name=self.__pulsedevice
            )
          self.__stream=self.__audio_obj #--引用对象 统一接口 
       else:
          debug_print("T is unknown type")
          pass #---------------------------------------
   
    def __destoryT(self):
       if self.__curtype == pyaudio.PyAudio:
          if self.__stream is not None:
            self.__stream.stop_stream()
            self.__stream.close()
            debug_print("__destory: pyaudio.PyAudio")
          if self.__audio_obj is not None:  
            self.__audio_obj.terminate()
            
       elif self.__curtype == pasimple.PaSimple:
            if self.__stream is not None:
              self.__stream.close()
              debug_print("__destory: pasimple.PaSimple")
                    
       self.__stream=None
       self.__audio_obj=None
    

    def __init__(self,queuewait=0.2,pipelen=1420,streamtimetout=5,queuelen=32,app_name='python stream player'):
        """
        流媒体播放器初始化构造函数
        :param queuewait: 队列获取数据的超时等待时间（秒）
        :param pipelen: 音频数据包长度 / 管道缓冲区大小（字节）
        :param streamtimetout: 流空闲超时时间，超时无数据自动退出（秒）
        :param queuelen: 播放队列个数 
        :param app_name: 在pulseaudio显示的应用名称
        """
        #flags 
        #[0]==1 退出线程, ==0 继续运行
        #[1] queue.get阻塞等待的秒数 默认0.2
        #[2]queue为empty时 持续多少秒后 退出
        self.__flags=[0,queuewait,streamtimetout]
        self.__pipelen = pipelen
        self.__retry=3
        self._app_name = app_name
        self.__lock=threading.Lock()
        self.__pa=None
        self.__que=queue.Queue(queuelen)
        self.__t_playpcm= None
        self.__proc_ffmpeg = None
        self.__t_readpipe= None

        self.__curtype=self.__Ttypelist
        self.__audio_obj:T
        self.__stream=None #用于播放流

        self.__pulseserver=None
        self.__pulsedevice=None
        self.__pyidx=0

        self.__pthd_t_readpipe=0

  

    def __del__(self): 
        self.__stop() 


    #参数pulseserver,pulsedevice 只适用于pasimeple类型 如果实例化类型为PyAudio 自动忽略这些参数
    #参数为 pyaudio指定播放设备索引 只适用于pyaudio.PyAudio类型 如果实例化类型为pasimeple 自动忽略该参数
    def play(self,input:str,ffvol=50,retry:int=3,block:bool=True,pulseserver:str=None,pulsedevice:str=None,pyidx:int=0)->None:
        """
        播放函数 

        Args:    
           param input: 一个流媒体url或本地文件路径 
           param ffvol: ffmpeg -vol选项 在使用ffmpeg解码时的音量
           param retry: 连接重试次数
           param isblock: 是否阻塞式 等待播放完成 这个选项与retry互斥,选择为 阻塞式才会继续根据retry重试, 非阻塞式直接返回不会retry
           param pulseserver: 指定pulse服务器地址 默认为None
           param pulsedevice: 指定pulse播放sink 可以为每个streamplayer_pulse实例指定不同sink播放 获取系统的pulse sink pactl list sinks short|awk '{print $2}'
        Return: 
           无返回值   
        """
      

        if self.__is_playing():
           return 


        if input == "" or input is None:
           debug_print("input is invalid")
           return
        
        ishttp=input.startswith(('http://', 'https://','HTTP://','HTTPS://'))
        

        #重置播放标记
        with self.__lock:
          self.__flags[0]=0
        
        self.__pulsedevice=pulsedevice
        self.__pulseserver=pulseserver
        self.__pyidx=pyidx
        self.__createT()
        
        self.__retry=retry
        for i in range(1,self.__retry+1):
           self.__t_playpcm=threading.Thread(target=self.__thd_pcm_write,daemon=True,name='thd_pcm_write')
           self.__t_playpcm.start()
            
           self.__proc_ffmpeg = subprocess.Popen(
           [
            "ffmpeg",
            "-i", input,        
            "-vol",str(ffvol),           #音量  
            "-f", "s16le",         # 输出 PCM 原始音频
            "-ar", "44100",        # 采样率write
            "-ac", "2",       
             "-acodec", "pcm_s16le",
            "-loglevel","quiet",
             "-y",
            "-"
           ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0)
   
           #os.set_blocking(self.__proc_ffmpeg.stdout.fileno(), False)
           #fcntl.fcntl(self.__proc_ffmpeg.stdout.fileno(), fcntl.F_SETFL, os.O_NDELAY)

           #linux
           '''
           fd=self.__proc_ffmpeg.stdout.fileno() 
           fl=fcntl.fcntl(fd,fcntl.F_GETFL)
           fcntl.fcntl(fd,fcntl.F_SETFL, fl | os.O_NONBLOCK)
           '''
         
           self.__t_readpipe=threading.Thread(target=self.__thd_pipe_read,daemon=True,name='thd_read_pipe')
           self.__t_readpipe.start()

           debug_print("starting to play.")

           if block:
             self.__t_playpcm.join()
           else:
             return   

           debug_print(f"streamplayer_pulse: play fault: {input},retry: {i}") 
       
    def __kill_ffmpeg(self):
            if self.__proc_ffmpeg is not None:
              if self.__proc_ffmpeg.poll() is None: 
                #self.__proc_ffmpeg.kill()  
                self.__proc_ffmpeg.terminate()
                self.__proc_ffmpeg.wait()
                debug_print("has killed ffmpeg\n")
              self.__proc_ffmpeg=None

    def __stop(self)->None:
            with self.__lock:
             self.__flags[0]=1

            self.__kill_ffmpeg()

            if self.__t_playpcm is not None:
                #self.__t_playpcm.join(timeout=max(2,self.__flags[1]))
                self.__t_playpcm.join() #-------------------------------------------------------
                self.__t_playpcm=None
                debug_print("__thd_pcm_write exitting. ")

            self.__destoryT()  
            
            if self.__pthd_t_readpipe !=0:
              libc.pthread_kill(self.__pthd_t_readpipe, signal.SIGUSR1)
              debug_print(f"pthread_kill: {self.__t_readpipe.name()}")
              
 #由于 pipe是阻塞式的 __thd_pipe_read 有概率阻塞 因此有py的gc自己回收 --可能内存泄露
            if self.__t_readpipe is not None:
              while self.__t_readpipe.is_alive(): 
                self.__t_readpipe.join(2) #----------------------------------------------------
                #self.__t_readpipe=None
                debug_print("__thd_pipe_read waitting exit.")
       
    def __is_playing(self)->bool:
           if self.__t_playpcm is not None:
             if self.__t_playpcm.is_alive():
                debug_print(f"thread: {self.__t_playpcm.name} is runing")
                return True
           return False
    
    def stop(self)->None:
       self.__stop() 
    
    def is_playing(self)->bool:
       return self.__is_playing()
    

def main():


 
 #s=streamplayer_pulse()

 #return

 #playurl2('http://127.0.0.1:18080/stream')
 #return

 #s=streamplayer[pasimple.PaSimple]()
 s=streamplayer[pyaudio.PyAudio]()
 s.play(input='http://127.0.0.1:18080/stream',retry=3,ffvol=50)

 #
'''
 s.play('http://127.0.0.1:18080/stream',block=False)
 time.sleep(15)
 s.stop()
'''

  
 
# s.play('http://127.0.0.1:18080/stream',retry=30)


'''
 s=streamplayer_pulse()
 s.play('http://127.0.0.1:18080/stream',pulsedevice='alsa_output.pci-0000_09_00.4.iec958-stereo')
'''
    

if __name__ == "__main__":
    main()
