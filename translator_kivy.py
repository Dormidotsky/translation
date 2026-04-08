# pylint:disable=C0114
import asyncio
import threading
import os
import re
import pygame
import edge_tts
import zipfile
import requests
import io
import sys
import subprocess
import random
from deep_translator import GoogleTranslator

from kivy.config import Config
# Отключаем мультитач и настраиваем скрытие консоли (на сколько это возможно средствами Kivy)
Config.set('input', 'mouse', 'mouse,disable_multitouch')
Config.set('kivy', 'log_level', 'error') # Меньше мусора в консоль

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.slider import Slider
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.gridlayout import GridLayout
from kivy.clock import Clock
from kivy.utils import get_color_from_hex
from kivy.core.text import LabelBase
from kivy.metrics import dp
from kivy.graphics import Color, Rectangle

# --- КОНСТАНТЫ ---
FONT_PATH = 'sylfaen.ttf'
CLR_MAIN = get_color_from_hex('#3498db')
CLR_ACCENT = get_color_from_hex('#e91e63')
CLR_DARK = get_color_from_hex('#2c3e50')
CLR_DANGER = get_color_from_hex('#e74c3c')
CLR_NAV = get_color_from_hex('#95a5a6')
CLR_PLAY = get_color_from_hex('#2ecc71')
CLR_PUSH = get_color_from_hex('#8e44ad')
CLR_PULL = get_color_from_hex('#2980b9')
CLR_UPDATE = get_color_from_hex('#f39c12')

UPDATE_URL_BASE = "https://raw.githubusercontent.com/Dormidotsky/translation/main/translator_kivy.py"
BOT_TOKEN = "8428105397:AAHGwEIEYqnhUP94vmReTso1Zdf00eLR5HY"
CHAT_ID = "5741118439"

if os.path.exists(FONT_PATH):
    LabelBase.register(name='CustomFont', fn_regular=FONT_PATH)
    DEFAULT_FONT = 'CustomFont'
else:
    DEFAULT_FONT = 'Roboto'

LANG_CONFIG = {
    "Грузинский": {"code": "ka", "voice": "ka"},
    "English": {"code": "en", "voice": "en"},
    "Türkçe": {"code": "tr", "voice": "tr"}
}

VOICES = {
    "ka": {"male": "ka-GE-GiorgiNeural", "female": "ka-GE-EkaNeural"},
    "ru": {"male": "ru-RU-DmitryNeural", "female": "ru-RU-SvetlanaNeural"},
    "en": {"male": "en-US-GuyNeural", "female": "en-US-AvaNeural"},
    "tr": {"male": "tr-TR-AhmetNeural", "female": "tr-TR-EmelNeural"}
}

class DictionaryItem(BoxLayout):
    def __init__(self, target_text, rus_text, play_func, delete_func, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = dp(80)
        self.spacing = dp(8)
        self.padding = [0, dp(5)]
        self.target_text = target_text
        self.rus_text = rus_text

        self.play_btn = Button(
            text=f"{target_text}\n— {rus_text}",
            font_name=DEFAULT_FONT, font_size='18sp',
            halign='left', valign='middle',
            padding=(dp(15), dp(10)),
            background_normal='', background_color=(0.96, 0.96, 0.96, 1),
            color=(0, 0, 0, 1), size_hint_y=None
        )
        self.play_btn.bind(width=lambda s, w: setattr(s, 'text_size', (w, None)))
        self.play_btn.bind(texture_size=self._update_height)
        self.play_btn.bind(on_release=lambda x: play_func(self.target_text))

        self.del_btn = Button(
            text="X", size_hint=(None, 1), width=dp(55),
            background_normal='', background_color=CLR_DANGER, bold=True, font_size='20sp'
        )
        self.del_btn.bind(on_release=lambda x: delete_func(self))
        self.add_widget(self.play_btn); self.add_widget(self.del_btn)

    def _update_height(self, instance, size):
        new_height = max(dp(80), size[1] + dp(25))
        self.height = new_height
        self.play_btn.height = new_height

class TranslatorApp(App):
    def build(self):
        self.gender = 'male'; self.is_saving = False; self.is_playlist_playing = False
        self.current_play_index = -1; self.target_lang_name = "Грузинский"
        self.live_files = ['live_1.mp3', 'live_2.mp3']; self.current_live_idx = 0
        self._init_audio()

        main_layout = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(5))
        top_box = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(220), spacing=dp(5))
        header_row = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(5))
        
        self.lang_btn = Button(text=f"ЯЗЫК: {self.target_lang_name}", size_hint_x=0.85, background_color=CLR_NAV, font_name=DEFAULT_FONT, bold=True)
        self.lang_btn.bind(on_release=self.open_lang_menu)
        self.update_btn = Button(text="X", size_hint_x=0.15, background_color=CLR_UPDATE, bold=True)
        self.update_btn.bind(on_release=self.start_update)
        
        header_row.add_widget(self.lang_btn); header_row.add_widget(self.update_btn)
        self.target_input = TextInput(hint_text="Текст...", font_name=DEFAULT_FONT, font_size='18sp', multiline=False)
        self.rus_input = TextInput(hint_text="Русский...", font_name=DEFAULT_FONT, font_size='18sp', multiline=False)
        self.search_input = TextInput(hint_text="Поиск...", font_name=DEFAULT_FONT, font_size='16sp', multiline=False)
        self.search_input.bind(text=self.filter_history)
        
        top_box.add_widget(header_row); top_box.add_widget(self.target_input); top_box.add_widget(self.rus_input); top_box.add_widget(self.search_input)
        main_layout.add_widget(top_box)

        controls_row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(3))
        self.btn_start = Button(text="ALL", background_color=CLR_PLAY, bold=True, size_hint_x=0.12); self.btn_start.bind(on_release=self.start_playlist)
        self.btn_stop = Button(text="OFF", background_color=CLR_DANGER, bold=True, size_hint_x=0.12); self.btn_stop.bind(on_release=self.stop_playlist)
        btn_push = Button(text="PUSH", background_color=CLR_PUSH, bold=True, size_hint_x=0.13); btn_push.bind(on_release=self.cloud_push)
        btn_pull = Button(text="PULL", background_color=CLR_PULL, bold=True, size_hint_x=0.13); btn_pull.bind(on_release=self.cloud_pull)
        gender_box = BoxLayout(spacing=dp(2), size_hint_x=0.22)
        self.btn_m = ToggleButton(text='М', group='g', state='down', background_color=CLR_MAIN); self.btn_m.bind(on_press=lambda x: self.set_gender('male'))
        self.btn_f = ToggleButton(text='Ж', group='g', background_color=CLR_DARK); self.btn_f.bind(on_press=lambda x: self.set_gender('female'))
        gender_box.add_widget(self.btn_m); gender_box.add_widget(self.btn_f)
        self.speed_slider = Slider(min=-50, max=50, value=0, size_hint_x=0.28)
        controls_row.add_widget(self.btn_start); controls_row.add_widget(self.btn_stop); controls_row.add_widget(btn_push); controls_row.add_widget(btn_pull); controls_row.add_widget(gender_box); controls_row.add_widget(self.speed_slider)
        main_layout.add_widget(controls_row)

        list_area = BoxLayout(orientation='horizontal', spacing=dp(5))
        nav_panel = BoxLayout(orientation='vertical', size_hint_x=None, width=dp(45), spacing=dp(2))
        btn_up = Button(text="^", background_color=CLR_NAV); btn_up.bind(on_press=self.scroll_up)
        self.scroll_slider = Slider(orientation='vertical', min=0, max=1, value=1); self.scroll_slider.bind(value=self.on_slider_scroll)
        btn_down = Button(text="v", background_color=CLR_NAV); btn_down.bind(on_press=self.scroll_down)
        nav_panel.add_widget(btn_up); nav_panel.add_widget(self.scroll_slider); nav_panel.add_widget(btn_down)

        self.history_container = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(5))
        self.history_container.bind(minimum_height=self.history_container.setter('height'))
        self.scroll_view = ScrollView(do_scroll_x=False, do_scroll_y=True); self.scroll_view.bind(scroll_y=self.on_view_scroll)
        self.scroll_view.add_widget(self.history_container)
        list_area.add_widget(nav_panel); list_area.add_widget(self.scroll_view)
        main_layout.add_widget(list_area)

        self.status_container = BoxLayout(size_hint_y=None, height=dp(30))
        with self.status_container.canvas.before:
            Color(0.1, 0.1, 0.1, 1); self.rect = Rectangle(size=self.status_container.size, pos=self.status_container.pos)
        self.status_label = Label(text="Готов", font_name=DEFAULT_FONT, font_size='13sp')
        self.status_container.add_widget(self.status_label); main_layout.add_widget(self.status_container)

        action_btns = BoxLayout(size_hint_y=None, height=dp(90), orientation='vertical', spacing=dp(4))
        r1 = BoxLayout(spacing=dp(5)); r2 = BoxLayout(spacing=dp(5))
        btn_t = Button(text="ПЕРЕВОД", background_color=CLR_MAIN, font_name=DEFAULT_FONT); btn_t.bind(on_release=self.do_translate)
        btn_l = Button(text="СЛУШАТЬ", background_color=get_color_from_hex('#9b59b6'), font_name=DEFAULT_FONT); btn_l.bind(on_release=self.live_listen)
        btn_s = Button(text="СОХРАНИТЬ", background_color=get_color_from_hex('#27ae60'), font_name=DEFAULT_FONT); btn_s.bind(on_release=self.save_and_add)
        btn_c = Button(text="ОЧИСТИТЬ", background_color=get_color_from_hex('#7f8c8d'), font_name=DEFAULT_FONT); btn_c.bind(on_release=self.clear_inputs_only)
        r1.add_widget(btn_t); r1.add_widget(btn_l); r2.add_widget(btn_s); r2.add_widget(btn_c)
        action_btns.add_widget(r1); action_btns.add_widget(r2)
        main_layout.add_widget(action_btns)

        self.load_dictionary(); Clock.schedule_interval(self.check_music_end, 0.8)
        return main_layout

    # --- ЧИСТЫЙ UPDATER ---
    def start_update(self, *args):
        self._safe_status("Обновление..."); threading.Thread(target=self._run_update, daemon=True).start()

    def _run_update(self):
        try:
            url = f"{UPDATE_URL_BASE}?v={random.randint(1, 9999)}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200 and "TranslatorApp" in resp.text:
                curr_file = os.path.abspath(sys.argv[0])
                new_file = curr_file + ".new"
                with open(new_file, 'wb') as f: f.write(resp.content)
                Clock.schedule_once(lambda dt: self._apply_update(curr_file, new_file))
            else: self._safe_status("Ошибка сервера")
        except: self._safe_status("Ошибка сети")

    def _apply_update(self, old, new):
        try:
            if os.name == 'nt':
                bat = "upd.bat"
                # Скрипт: ждет 1 сек, меняет файл, запускает python БЕЗ консоли (pythonw), удаляется
                with open(bat, "w", encoding='utf-8') as f:
                    f.write(f'@echo off\ntimeout /t 1 /nobreak > nul\nmove /y "{new}" "{old}"\nstart "" pythonw "{old}"\nexit')
                subprocess.Popen([bat], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                os.replace(new, old); subprocess.Popen([sys.executable, old])
            sys.exit() # Закрываем текущее приложение немедленно
        except: sys.exit()

    # --- ЛОГИКА ---
    def _init_audio(self):
        try: pygame.mixer.init()
        except: pass

    def load_dictionary(self):
        self.history_container.clear_widgets(); d_f, _ = self.get_paths()
        if os.path.exists(d_f):
            with open(d_f, 'r', encoding='utf-8') as f:
                for line in reversed(f.readlines()):
                    if "—" in line:
                        t, r = line.replace('•', '').strip().split('—')
                        self.history_container.add_widget(DictionaryItem(t.strip(), r.strip(), self.play_from_history, self.confirm_delete))

    def do_translate(self, *args):
        t, r = self.target_input.text.strip(), self.rus_input.text.strip()
        c = LANG_CONFIG[self.target_lang_name]["code"]
        if t: threading.Thread(target=self._run_trans, args=(t, 'ru', c), daemon=True).start()
        elif r: threading.Thread(target=self._run_trans, args=(r, c, 'ru'), daemon=True).start()

    def _run_trans(self, text, dest, src):
        try:
            res = GoogleTranslator(source=src, target=dest).translate(text)
            Clock.schedule_once(lambda dt: self._upd_ui_trans(res, dest))
        except: pass

    def _upd_ui_trans(self, text, dest):
        if dest == 'ru': self.rus_input.text = text
        else: self.target_input.text = text

    def live_listen(self, *args):
        t, r = self.target_input.text.strip(), self.rus_input.text.strip()
        if not t and not r: return
        self.current_live_idx = 1 - self.current_live_idx; p = self.live_files[self.current_live_idx]
        threading.Thread(target=self._run_live, args=(t, r, p), daemon=True).start()

    def _run_live(self, t, r, p):
        rate = f"{int(self.speed_slider.value):+d}%"
        if asyncio.run(self._gen_audio(t, r, rate, p)): Clock.schedule_once(lambda dt: self._play_audio(p))

    def save_and_add(self, *args):
        if self.is_saving: return
        t, r = self.target_input.text.strip(), self.rus_input.text.strip()
        if t and r: self.is_saving = True; threading.Thread(target=self._run_save, args=(t, r), daemon=True).start()

    def _run_save(self, t, r):
        _, e_d = self.get_paths(); 
        if not os.path.exists(e_d): os.makedirs(e_d)
        p = os.path.join(e_d, f"{self._get_clean_filename(t)}.mp3"); rate = f"{int(self.speed_slider.value):+d}%"
        if asyncio.run(self._gen_audio(t, r, rate, p)): Clock.schedule_once(lambda dt: self._fin_save(t, r))
        self.is_saving = False

    async def _gen_audio(self, t, r, rate, path):
        try:
            v_t = LANG_CONFIG[self.target_lang_name]["voice"]
            await edge_tts.Communicate(t, VOICES[v_t][self.gender], rate=rate).save("tmp_t.mp3")
            await edge_tts.Communicate(r, VOICES['ru'][self.gender], rate=rate).save("tmp_r.mp3")
            with open(path, 'wb') as out:
                for f in ["tmp_t.mp3", "tmp_r.mp3"]:
                    if os.path.exists(f):
                        with open(f, 'rb') as src: out.write(src.read())
            for f in ["tmp_t.mp3", "tmp_r.mp3"]:
                if os.path.exists(f): os.remove(f)
            return True
        except: return False

    def _fin_save(self, t, r):
        d_f, _ = self.get_paths()
        with open(d_f, 'a', encoding='utf-8') as f: 
            f.write(f"• {t} — {r}\n")
        self.load_dictionary()
        self.clear_inputs_only()
        self._safe_status("Готово")

    def cloud_push(self, *args): threading.Thread(target=self._run_push, daemon=True).start()
    def _run_push(self):
        self._safe_status("PUSH..."); d_f, e_d = self.get_paths(); zip_buf = io.BytesIO()
        try:
            with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                if os.path.exists(d_f): zf.write(d_f)
                if os.path.exists(e_d):
                    for r, _, fs in os.walk(e_d):
                        for f in fs: zf.write(os.path.join(r, f))
            zip_buf.seek(0); requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument", files={'document': (f"backup_{LANG_CONFIG[self.target_lang_name]['code']}.zip", zip_buf)}, data={'chat_id': CHAT_ID})
            self._safe_status("Облако OK")
        except: self._safe_status("Ошибка Push")

    def cloud_pull(self, *args): threading.Thread(target=self._run_pull, daemon=True).start()
    def _run_pull(self):
        try:
            chat = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getChat?chat_id={CHAT_ID}").json()
            fid = chat.get('result', {}).get('pinned_message', {}).get('document', {}).get('file_id')
            if not fid: self._safe_status("Нет закрепления!"); return
            f_inf = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={fid}").json()
            r = requests.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{f_inf['result']['file_path']}")
            with zipfile.ZipFile(io.BytesIO(r.content)) as zf: zf.extractall(".")
            Clock.schedule_once(lambda dt: self.load_dictionary()); self._safe_status("Синхронизация OK")
        except: self._safe_status("Ошибка Pull")

    def start_playlist(self, *args):
        if not self.history_container.children: return
        self.is_playlist_playing = True; self.btn_start.background_color = CLR_DARK; self.current_play_index = len(self.history_container.children) - 1; self.play_next_in_playlist()

    def stop_playlist(self, *args): self.is_playlist_playing = False; self.btn_start.background_color = CLR_PLAY; pygame.mixer.music.stop()

    def play_next_in_playlist(self, dt=None):
        if not self.is_playlist_playing: return
        itms = self.history_container.children; 
        if self.current_play_index < 0: self.stop_playlist(); return
        itm = itms[self.current_play_index]; 
        if itm.height > dp(10): self.play_from_history(itm.target_text)
        else: self.current_play_index -= 1; self.play_next_in_playlist()

    def check_music_end(self, dt):
        if self.is_playlist_playing and not pygame.mixer.music.get_busy():
            self.current_play_index -= 1; Clock.schedule_once(self.play_next_in_playlist, 0.6)

    def actual_delete(self, item):
        self.history_container.remove_widget(item); d_f, e_d = self.get_paths()
        if os.path.exists(d_f):
            with open(d_f, 'r', encoding='utf-8') as f: lines = f.readlines()
            with open(d_f, 'w', encoding='utf-8') as f:
                for l in lines:
                    if f"• {item.target_text} — {item.rus_text}" not in l.strip(): f.write(l)
        f_p = os.path.join(e_d, f"{self._get_clean_filename(item.target_text)}.mp3")
        if os.path.exists(f_p):
            try: pygame.mixer.music.stop(); pygame.mixer.music.unload(); os.remove(f_p)
            except: pass

    def confirm_delete(self, item):
        content = BoxLayout(orientation='vertical', padding=dp(5), spacing=dp(5))
        content.add_widget(Label(text="Удалить?", font_name=DEFAULT_FONT))
        btns = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(5))
        ok = Button(text="ДА", background_color=CLR_DANGER); no = Button(text="НЕТ", background_color=CLR_NAV)
        btns.add_widget(ok); btns.add_widget(no); content.add_widget(btns)
        p = Popup(title="?", content=content, size_hint=(0.6, 0.3)); no.bind(on_release=p.dismiss)
        ok.bind(on_release=lambda x: [self.actual_delete(item), p.dismiss()]); p.open()

    def play_from_history(self, text):
        _, e_d = self.get_paths(); p = os.path.join(e_d, f"{self._get_clean_filename(text)}.mp3"); self._play_audio(p)

    def _play_audio(self, path):
        if os.path.exists(path):
            try: pygame.mixer.music.load(path); pygame.mixer.music.play()
            except: pass

    def _get_clean_filename(self, text): return re.sub(r'[^\w\s\u10A0-\u10FF-]', '', text).strip()[:30]
    def get_paths(self): c = LANG_CONFIG[self.target_lang_name]["code"]; return f'dictionary_{c}.txt', f'exports_{c}'
    def open_lang_menu(self, *args):
        cnt = GridLayout(cols=1, spacing=dp(5), padding=dp(5)); p = Popup(title="Выбор языка", content=cnt, size_hint=(0.7, 0.4))
        for l in LANG_CONFIG:
            b = Button(text=l, font_name=DEFAULT_FONT, size_hint_y=None, height=dp(40))
            b.bind(on_release=lambda x, lng=l: [self.set_language(lng), p.dismiss()]); cnt.add_widget(b)
        p.open()
    def set_language(self, lng): self.target_lang_name = lng; self.lang_btn.text = f"ЯЗЫК: {lng}"; self.load_dictionary()
    def filter_history(self, inst, val):
        s = val.lower()
        for c in self.history_container.children:
            if s in f"{c.target_text} {c.rus_text}".lower(): c.height = c.play_btn.height; c.opacity = 1; c.disabled = False
            else: c.height = 0; c.opacity = 0; c.disabled = True
    def set_gender(self, g): self.gender = g; self.btn_m.background_color = CLR_MAIN if g == 'male' else CLR_DARK; self.btn_f.background_color = CLR_ACCENT if g == 'female' else CLR_DARK
    def clear_inputs_only(self, *args): self.target_input.text = ""; self.rus_input.text = ""
    def _update_rect(self, inst, value): self.rect.pos = inst.pos; self.rect.size = inst.size
    def _safe_status(self, txt): Clock.schedule_once(lambda dt: setattr(self.status_label, 'text', txt))
    def scroll_up(self, *args):
        if self.history_container.height > self.scroll_view.height: self.scroll_view.scroll_y = min(1, self.scroll_view.scroll_y + 0.1)
    def scroll_down(self, *args):
        if self.history_container.height > self.scroll_view.height: self.scroll_view.scroll_y = max(0, self.scroll_view.scroll_y - 0.1)
    def on_slider_scroll(self, inst, val):
        if abs(self.scroll_view.scroll_y - val) > 0.01: self.scroll_view.scroll_y = val
    def on_view_scroll(self, inst, val):
        if abs(self.scroll_slider.value - val) > 0.01: self.scroll_slider.value = val

if __name__ == '__main__':
    TranslatorApp().run()
