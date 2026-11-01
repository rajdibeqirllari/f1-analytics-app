import hashlib
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
from services.video_3d_overlay import encode_frames
from test_video_comparison import comparison_fixture


@unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg missing')
class StreamingRenderTests(unittest.TestCase):
    def test_streamed_frames_match_sequential_output_exactly(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as temp:
            folder=Path(temp);frames=folder/'frames';frames.mkdir()
            done=threading.Event();c=comparison_fixture()
            options=dict(size=(540,960),fps=24,start=0,end=3/24,frames=3,full=False)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(encode_frames,c,frames,folder/'stream.mp4',producer_done=done,require_ready=True,**options)
                try:
                    for i in range(3):
                        time.sleep(.04)
                        Image.new('RGB',options['size'],(i*50,30,60)).save(frames/f'frame_{i+1:04d}.png',compress_level=0)
                        (frames/f'frame_{i+1:04d}.ready').touch()
                    self.assertFalse((folder/'stream.mp4').exists())
                finally:done.set()
                future.result(timeout=30)
            encode_frames(c,frames,folder/'serial.mp4',**options)
            self.assertEqual(hashlib.sha256((folder/'stream.mp4').read_bytes()).digest(),
                             hashlib.sha256((folder/'serial.mp4').read_bytes()).digest())

    def test_failed_producer_never_publishes_output(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as temp:
            folder=Path(temp);done=threading.Event();done.set()
            output=folder/'broken.mp4'
            with self.assertRaisesRegex(RuntimeError,'incomplete'):
                encode_frames(comparison_fixture(),folder,output,size=(540,960),fps=24,start=0,end=1,
                              frames=24,full=False,producer_done=done)
            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix('.partial.mp4').exists())
