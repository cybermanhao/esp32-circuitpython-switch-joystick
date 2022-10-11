import time
from adafruit_hid import find_device
import asyncio
from hid.joystick.input.pro_controller import JoyStickInput_PRO_CONTROLLER
from hid.joystick.joystick import JoyStick
import usb_hid

_Mini_Key_Send_Span_ns = 3000000

class JoyStick_PRO_CONTROLLER(JoyStick):
    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, '_instance'):
            cls._instance = super(JoyStick_PRO_CONTROLLER, cls).__new__(cls)
        return cls._instance

    _first = True

    def __init__(self):
        if self._first:
            self._first = False
            self._joystick_device = find_device(
                usb_hid.devices, usage_page=0x1, usage=0x04)
            self._last_send_monotonic_ns = 0
            self._realtime_data_lock = asyncio.Lock()
            self._is_realtime = False
            self._realtime_action = ""
            self._realtime_task = None
            try:
                self._sync_release()
            except OSError:
                time.sleep(1)
                self._sync_release()

    def _sync_release(self):
        self._sync_send(JoyStickInput_PRO_CONTROLLER(""))

    def _sync_send(self,input:JoyStickInput_PRO_CONTROLLER):
        self._joystick_device.send_report(input.buffer())
        self._last_send_monotonic_ns = time.monotonic_ns()


    async def _send(self,  input_line: str = "",earliest_send_key_monotonic_ns=0):
        earliest = self._last_send_monotonic_ns + _Mini_Key_Send_Span_ns
        if earliest < earliest_send_key_monotonic_ns:
            earliest = earliest_send_key_monotonic_ns
        input = JoyStickInput_PRO_CONTROLLER(input_line)
        loop = 0
        while True:
            loop += 1
            now = time.monotonic_ns()
            if now >= earliest:
                break
            elif now < earliest - _Mini_Key_Send_Span_ns:
                ms = int((earliest - now  - _Mini_Key_Send_Span_ns)/1000000)
                await asyncio.sleep_ms(ms)
            else:
                time.sleep(0.0001)
        # print((time.monotonic_ns() - earliest)/1000000,loop,input_line)
        self._sync_send(input)

    async def release(self,release_monotonic_ns:float = 0):
        await self._send("",release_monotonic_ns)

    async def key_press(self,  input_line: str = "", keep: float = 0.005):
        await self._send(input_line,0)
        release_monotonic_ns = self._last_send_monotonic_ns + keep*1000000000
        await self.release(release_monotonic_ns)

    async def do_action(self,  action_line: str = ""):
        splits = action_line.split(":")
        if len(splits) > 2:
            await self.release()
            return
        if len(splits) == 1:
            try:
                keep = float(splits[0])
                await self.key_press("", keep)
            except:
                await self.key_press(splits[0], 0.1)
        else:
            keep = 0.1
            try:
                keep = float(splits[1])
            except:
                pass
            await self.key_press(splits[0], keep)

    def start_realtime(self):
        if self._realtime_task:
            return
        self._is_realtime = True
        self._realtime_task = asyncio.create_task(self._start_realtime_async())

    def stop_realtime(self):
        self._is_realtime = False
        self._realtime_task = None

    async def _start_realtime_async(self):
        async with self._realtime_data_lock:
            self._realtime_action = ""
        await self._send(self._realtime_action)
        last_action = ""
        last_action_monotonic = time.monotonic()
        while self._is_realtime:
            await asyncio.sleep_ms(int(_Mini_Key_Send_Span_ns/1000000))
            action = None
            if time.monotonic()-last_action_monotonic > 2:
                last_action = "clear"
            async with self._realtime_data_lock:
                if self._realtime_action != last_action:
                    action = self._realtime_action
                    last_action = action
                    last_action_monotonic = time.monotonic()
            if action != None:
                await self._send(action)
        await self._send("")


    async def send_realtime_action(self,action:str):
        async with self._realtime_data_lock:
            self._realtime_action = action.strip()

    async def _stop_realtime_async(self):
        self._is_realtime = False
        if not self._realtime_task:
            return
        await self._realtime_task
        self._realtime_task = None