r"""
Number Dictation Trainer

A small Python app for listening practice:
- Choose a number range
- Choose a spoken language
- Generate a random number
- Hear the number spoken aloud
- Type what you heard
- Get marked correct/incorrect

Open-source/local-friendly stack:
- tkinter: built into Python for the GUI
- pyttsx3: offline text-to-speech engine
- gTTS: cleaner online text-to-speech using Google Translate TTS
- num2words: converts numbers into words in many languages

Create and use a local virtual environment:

macOS/Linux:
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    pip install pyttsx3 num2words gTTS
    python number_dictation_trainer.py

Windows PowerShell:
    py -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install pyttsx3 num2words gTTS
    python number_dictation_trainer.py

After you are done:
    deactivate

Notes:
- pyttsx3 uses voices installed on your computer. You may need to install extra system voices
  for Italian/German/French/etc.
- On macOS, system voices can be managed in System Settings > Accessibility > Spoken Content > System Voice.
"""

from __future__ import annotations

import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk, messagebox

import pyttsx3
from gtts import gTTS
from num2words import num2words


@dataclass(frozen=True)
class LanguageOption:
    label: str
    num2words_code: str
    voice_keywords: tuple[str, ...]


LANGUAGES: dict[str, LanguageOption] = {
    "Italian": LanguageOption("Italian", "it", ("italian", "italiano", "it_", "lucia", "alice")),
    "English": LanguageOption("English", "en", ("english", "en_", "samantha", "alex", "daniel")),
    "French": LanguageOption("French", "fr", ("french", "français", "fr_", "thomas", "amelie")),
    "German": LanguageOption("German", "de", ("german", "deutsch", "de_", "anna")),
    "Spanish": LanguageOption("Spanish", "es", ("spanish", "español", "es_", "monica", "jorge")),
}


class SpeechEngine:
    def __init__(self) -> None:
        self.engine = pyttsx3.init()
        self.voices = self.engine.getProperty("voices") or []
        self.lock = threading.Lock()

    def set_voice_for_language(self, language: LanguageOption) -> str | None:
        """Try to select a system TTS voice matching the chosen language."""
        keywords = tuple(k.lower() for k in language.voice_keywords)

        for voice in self.voices:
            haystack = " ".join(
                str(part).lower()
                for part in [
                    getattr(voice, "id", ""),
                    getattr(voice, "name", ""),
                    getattr(voice, "languages", ""),
                ]
            )
            if any(keyword in haystack for keyword in keywords):
                self.engine.setProperty("voice", voice.id)
                return getattr(voice, "name", voice.id)

        return None

    def speak_offline(self, text: str, rate: int, volume: float, language: LanguageOption) -> str | None:
        """Speak with pyttsx3. Fully offline, but voice quality depends on system voices."""
        selected_voice = self.set_voice_for_language(language)
        self.engine.setProperty("rate", rate)
        self.engine.setProperty("volume", volume)
        self.engine.say(text)
        self.engine.runAndWait()
        return selected_voice

    def speak_gtts(self, text: str, language: LanguageOption) -> str:
        """Speak with gTTS. Cleaner voice, but requires internet."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
            filename = temp_audio.name

        try:
            tts = gTTS(text=text, lang=language.num2words_code, slow=False)
            tts.save(filename)
            self.play_audio_file(filename)
            return "gTTS / Google Translate voice"
        finally:
            try:
                os.remove(filename)
            except OSError:
                pass

    def play_audio_file(self, filename: str) -> None:
        if sys.platform == "darwin":
            subprocess.run(["afplay", filename], check=True)
        elif sys.platform.startswith("win"):
            os.startfile(filename)  # type: ignore[attr-defined]
        else:
            players = (["mpg123", filename], ["ffplay", "-nodisp", "-autoexit", filename], ["xdg-open", filename])
            last_error: Exception | None = None
            for command in players:
                try:
                    subprocess.run(command, check=True)
                    return
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
            raise RuntimeError(f"Could not play audio file. Last error: {last_error}")

    def speak(self, text: str, rate: int, volume: float, language: LanguageOption, engine_name: str) -> str | None:
        """Speak in a background-safe way. Returns selected voice name if found."""
        with self.lock:
            if engine_name == "Cleaner online voice - gTTS":
                return self.speak_gtts(text, language)
            return self.speak_offline(text, rate=rate, volume=volume, language=language)


class NumberDictationTrainer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Number Dictation Trainer")
        self.geometry("720x520")
        self.minsize(660, 480)

        self.speech = SpeechEngine()
        self.current_number: int | None = None
        self.current_spoken_text: str = ""
        self.correct_count = 0
        self.total_count = 0

        self.min_var = tk.StringVar(value="1")
        self.max_var = tk.StringVar(value="1000")
        self.language_var = tk.StringVar(value="Italian")
        self.tts_engine_var = tk.StringVar(value="Cleaner online voice - gTTS")
        self.answer_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Choose a range, then press New Number.")
        self.voice_var = tk.StringVar(value="Voice: not selected yet")
        self.rate_var = tk.IntVar(value=145)
        self.show_answer_var = tk.BooleanVar(value=False)

        self._build_ui()
        self.bind("<Return>", lambda event: self.check_answer())
        self.bind("<Command-r>", lambda event: self.replay_number())
        self.bind("<Control-r>", lambda event: self.replay_number())

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(outer, text="Number Dictation Trainer", font=("Arial", 24, "bold"))
        title.pack(anchor="w")

        subtitle = ttk.Label(
            outer,
            text="Hear a random number, type what you heard, then check your answer.",
            font=("Arial", 12),
        )
        subtitle.pack(anchor="w", pady=(2, 18))

        settings = ttk.LabelFrame(outer, text="Settings", padding=14)
        settings.pack(fill="x")

        ttk.Label(settings, text="Minimum").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.min_var, width=12).grid(row=1, column=0, sticky="w", padx=(0, 16))

        ttk.Label(settings, text="Maximum").grid(row=0, column=1, sticky="w")
        ttk.Entry(settings, textvariable=self.max_var, width=12).grid(row=1, column=1, sticky="w", padx=(0, 16))

        ttk.Label(settings, text="Language").grid(row=0, column=2, sticky="w")
        lang_box = ttk.Combobox(
            settings,
            textvariable=self.language_var,
            values=list(LANGUAGES.keys()),
            state="readonly",
            width=14,
        )
        lang_box.grid(row=1, column=2, sticky="w", padx=(0, 16))

        ttk.Label(settings, text="Voice engine").grid(row=0, column=3, sticky="w")
        engine_box = ttk.Combobox(
            settings,
            textvariable=self.tts_engine_var,
            values=["Cleaner online voice - gTTS", "Offline system voice - pyttsx3"],
            state="readonly",
            width=28,
        )
        engine_box.grid(row=1, column=3, sticky="w", padx=(0, 16))

        ttk.Label(settings, text="Offline speech speed").grid(row=2, column=0, sticky="w", pady=(12, 0))
        ttk.Scale(settings, from_=90, to=220, variable=self.rate_var, orient="horizontal", length=150).grid(
            row=3, column=0, columnspan=2, sticky="w"
        )

        ttk.Checkbutton(settings, text="Show answer after checking", variable=self.show_answer_var).grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(12, 0)
        )

        main = ttk.Frame(outer, padding=(0, 20, 0, 0))
        main.pack(fill="both", expand=True)

        button_row = ttk.Frame(main)
        button_row.pack(fill="x")

        ttk.Button(button_row, text="New Number", command=self.new_number).pack(side="left", padx=(0, 10))
        ttk.Button(button_row, text="Replay", command=self.replay_number).pack(side="left", padx=(0, 10))
        ttk.Button(button_row, text="Check", command=self.check_answer).pack(side="left", padx=(0, 10))
        ttk.Button(button_row, text="Reveal", command=self.reveal_answer).pack(side="left", padx=(0, 10))
        ttk.Button(button_row, text="Reset Score", command=self.reset_score).pack(side="left")

        answer_frame = ttk.LabelFrame(main, text="Your answer", padding=14)
        answer_frame.pack(fill="x", pady=(20, 0))

        answer_entry = ttk.Entry(answer_frame, textvariable=self.answer_var, font=("Arial", 22), width=20)
        answer_entry.pack(fill="x")
        answer_entry.focus()

        hint = ttk.Label(
            answer_frame,
            text="Tip: type digits, e.g. 275. Press Enter to check. Press Cmd/Ctrl+R to replay.",
        )
        hint.pack(anchor="w", pady=(8, 0))

        result_frame = ttk.Frame(main)
        result_frame.pack(fill="x", pady=(22, 0))

        self.status_label = ttk.Label(result_frame, textvariable=self.status_var, font=("Arial", 16, "bold"))
        self.status_label.pack(anchor="w")

        self.score_label = ttk.Label(result_frame, text="Score: 0 / 0", font=("Arial", 12))
        self.score_label.pack(anchor="w", pady=(8, 0))

        voice_label = ttk.Label(result_frame, textvariable=self.voice_var, font=("Arial", 10))
        voice_label.pack(anchor="w", pady=(8, 0))

        self.spoken_label = ttk.Label(result_frame, text="", font=("Arial", 12), wraplength=650)
        self.spoken_label.pack(anchor="w", pady=(10, 0))

    def parse_range(self) -> tuple[int, int] | None:
        try:
            min_value = int(self.min_var.get().strip())
            max_value = int(self.max_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid range", "Minimum and maximum must be whole numbers.")
            return None

        if min_value > max_value:
            messagebox.showerror("Invalid range", "Minimum must be less than or equal to maximum.")
            return None

        return min_value, max_value

    def language(self) -> LanguageOption:
        return LANGUAGES[self.language_var.get()]

    def new_number(self) -> None:
        parsed = self.parse_range()
        if parsed is None:
            return

        min_value, max_value = parsed
        self.current_number = random.randint(min_value, max_value)
        self.current_spoken_text = self.number_to_words(self.current_number)
        self.answer_var.set("")
        self.spoken_label.config(text="")
        self.status_var.set("Listen, then type the number you heard.")
        self.replay_number()

    def number_to_words(self, number: int) -> str:
        language = self.language()
        try:
            return num2words(number, lang=language.num2words_code)
        except NotImplementedError:
            return str(number)

    def replay_number(self) -> None:
        if self.current_number is None:
            self.new_number()
            return

        language = self.language()
        text = self.current_spoken_text or self.number_to_words(self.current_number)
        rate = self.rate_var.get()

        def worker() -> None:
            try:
                selected_voice = self.speech.speak(
                    text,
                    rate=rate,
                    volume=1.0,
                    language=language,
                    engine_name=self.tts_engine_var.get(),
                )
                voice_text = f"Voice: {selected_voice}" if selected_voice else "Voice: no matching system voice found; using default voice"
                self.after(0, lambda: self.voice_var.set(voice_text))
            except Exception as exc:  # noqa: BLE001 - friendly GUI error
                self.after(0, lambda: messagebox.showerror("Speech error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def normalize_answer(self, answer: str) -> str:
        # Accept things like "2 75", "275.", "275,", etc.
        return re.sub(r"[^0-9-]", "", answer.strip())

    def check_answer(self) -> None:
        if self.current_number is None:
            self.status_var.set("Press New Number first.")
            return

        raw_answer = self.answer_var.get()
        normalized = self.normalize_answer(raw_answer)

        if normalized in {"", "-"}:
            self.status_var.set("Type the number you heard first.")
            return

        try:
            guessed_number = int(normalized)
        except ValueError:
            self.status_var.set("Please type the answer as digits, like 275.")
            return

        self.total_count += 1

        if guessed_number == self.current_number:
            self.correct_count += 1
            self.status_var.set(f"Correct ✅  {self.current_number}")
        else:
            self.status_var.set(f"Incorrect ❌  You wrote {guessed_number}; correct was {self.current_number}")

        self.update_score()

        if self.show_answer_var.get():
            self.spoken_label.config(text=f"Spoken form: {self.current_spoken_text}")

    def reveal_answer(self) -> None:
        if self.current_number is None:
            self.status_var.set("No number yet.")
            return
        self.status_var.set(f"Answer: {self.current_number}")
        self.spoken_label.config(text=f"Spoken form: {self.current_spoken_text}")

    def reset_score(self) -> None:
        self.correct_count = 0
        self.total_count = 0
        self.update_score()
        self.status_var.set("Score reset.")

    def update_score(self) -> None:
        percentage = 0 if self.total_count == 0 else round((self.correct_count / self.total_count) * 100)
        self.score_label.config(text=f"Score: {self.correct_count} / {self.total_count} ({percentage}%)")


if __name__ == "__main__":
    app = NumberDictationTrainer()
    app.mainloop()
