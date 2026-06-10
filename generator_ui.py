import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import random
import subprocess
import os
import threading
import re
from datetime import datetime

import matplotlib
matplotlib.use("TkAgg")  # backend pod wykres w oknie tk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


def _parsuj_linie_stats(linia):
    """wyciaga stats z pierwszej linii wynik.txt albo none"""
    s = linia.strip().lstrip("\ufeff")
    m = re.match(
        r"STATS:\s*Dlugosc=\[(\d+)\],\s*LiczbaKonfliktow=\[(\d+)\],\s*CzasObliczen=\[([0-9.]+)\]\s*s",
        s,
    )
    if not m:
        return None
    return {
        "dlugosc": int(m.group(1)),
        "konflikty": int(m.group(2)),
        "czas_obliczen": float(m.group(3)),
    }


_RE_CHART = re.compile(r"^CHART:\s*(\d+)\s*,\s*(\d+)\s*$", re.IGNORECASE)


class TabuSearchUI:
    def __init__(self, root):
        self.root = root
        self._proj_dir = os.path.dirname(os.path.abspath(__file__))
        self.root.title("Problem VII - generator instancji")
        self.root.geometry("640x720")
        self.root.minsize(520, 580)

        self.okno_wynikow = None
        self._chart_iter = []
        self._chart_best = []
        self._chart_iter_limit = 100000
        self._chart_global_best = None  # najlepsza dlugosc ze wszystkich watkow
        self._ostatnia_iteracja = 0
        self._chart_pad_x_frac = 0.04  # margines osi x na wykresie
        self._chart_pad_y_frac = 0.18  # margines osi y zeby schodki byly czytelne
        self._snapshot_raport = None
        self._ostatni_wynik_tekst = ""
        self.wstrzykniete_bledy = 0
        self.is_running = False

        self._build_okno_glowne()
        self._utworz_okno_wynikow()

        self.root.protocol("WM_DELETE_WINDOW", self._zamknij_aplikacje)

    def _build_okno_glowne(self):
        main = tk.Frame(self.root, padx=12, pady=10)
        main.pack(fill=tk.BOTH, expand=True)

        tk.Label(main, text="Generator instancji", font=("Arial", 14, "bold")).pack(
            anchor="w", pady=(0, 6)
        )

        frame_params = tk.Frame(main)
        frame_params.pack(anchor="w", pady=4)

        tk.Label(frame_params, text="Liczba sekwencji m:").grid(row=0, column=0, sticky="e", padx=4, pady=2)
        self.entry_m = tk.Entry(frame_params, width=10)
        self.entry_m.insert(0, "10")
        self.entry_m.grid(row=0, column=1, pady=2)

        tk.Label(frame_params, text="Długość sekwencji n:").grid(row=1, column=0, sticky="e", padx=4, pady=2)
        self.entry_n = tk.Entry(frame_params, width=10)
        self.entry_n.insert(0, "50")
        self.entry_n.grid(row=1, column=1, pady=2)

        tk.Label(frame_params, text="Długość nadciągu d:").grid(row=2, column=0, sticky="e", padx=4, pady=2)
        self.entry_d = tk.Entry(frame_params, width=10)
        self.entry_d.insert(0, "60")
        self.entry_d.grid(row=2, column=1, pady=2)

        tk.Label(frame_params, text="Alfabet:").grid(row=3, column=0, sticky="e", padx=4, pady=2)
        self.combo_alfabet = ttk.Combobox(
            frame_params,
            values=["ACGT (Pełny)", "AC (Uproszczony)"],
            state="readonly",
            width=18,
        )
        self.combo_alfabet.set("ACGT (Pełny)")
        self.combo_alfabet.grid(row=3, column=1, pady=2)

        frame_gen = tk.Frame(main)
        frame_gen.pack(fill=tk.X, pady=6)
        tk.Button(
            frame_gen,
            text="Wygeneruj czystą instancję",
            command=self.generuj,
            bg="#b3e5fc",
            font=("Arial", 10, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        tk.Button(
            frame_gen,
            text="Pusty wzorzec (Wyczyść)",
            command=self.wyczysc_wzorzec,
            font=("Arial", 10),
        ).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(frame_gen, text="Liczba mutacji:").pack(side=tk.LEFT)
        self.entry_errors = tk.Entry(frame_gen, width=5)
        self.entry_errors.insert(0, "5")
        self.entry_errors.pack(side=tk.LEFT, padx=4)
        tk.Button(
            frame_gen,
            text="Dodaj mutacje",
            command=self.wstrzyknij_bledy,
            bg="#ffcdd2",
            font=("Arial", 10),
        ).pack(side=tk.LEFT)

        self.lbl_optimum = tk.Label(
            main, text="Znane optimum: -", fg="green", font=("Arial", 10, "bold")
        )
        self.lbl_optimum.pack(anchor="w", pady=(0, 4))

        tk.Label(
            main,
            text="Sekwencje wejściowe (możesz edytować ręcznie):",
            font=("Arial", 10, "bold"),
        ).pack(anchor="w", pady=(8, 4))
        self.text_in = tk.Text(main, height=10, width=72, font=("Courier", 12))
        self.text_in.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        ttk.Separator(main, orient="horizontal").pack(fill=tk.X, pady=8)

        tk.Label(main, text="Tabu Search (silnik C++)", font=("Arial", 14, "bold")).pack(
            anchor="w", pady=(0, 6)
        )

        frame_perf = tk.Frame(main)
        frame_perf.pack(anchor="w", pady=4)

        tk.Label(frame_perf, text="Liczba wątków:").grid(row=0, column=0, padx=4, pady=4)
        self.entry_threads = tk.Entry(frame_perf, width=6)
        self.entry_threads.insert(0, str(os.cpu_count() or 4))
        self.entry_threads.grid(row=0, column=1, pady=4)

        tk.Label(frame_perf, text="Limit czasu [s]:").grid(row=0, column=2, padx=(16, 4), pady=4)
        self.entry_time = tk.Entry(frame_perf, width=6)
        self.entry_time.insert(0, "15")
        self.entry_time.grid(row=0, column=3, pady=4)

        tk.Label(frame_perf, text="Limit iteracji:").grid(row=0, column=4, padx=(16, 4), pady=4)
        self.entry_iter = tk.Entry(frame_perf, width=10)
        self.entry_iter.insert(0, "100000")
        self.entry_iter.grid(row=0, column=5, pady=4)

        frame_run = tk.Frame(main)
        frame_run.pack(fill=tk.X, pady=12)
        self.btn_run = tk.Button(
            frame_run,
            text="Uruchom obliczenia",
            command=self.uruchom_cpp,
            bg="#ff9800",
            font=("Arial", 13, "bold"),
            height=2,
        )
        self.btn_run.pack(side=tk.LEFT)
        tk.Button(
            frame_run,
            text="Pokaż okno wyników",
            command=self._pokaz_okno_wynikow,
            font=("Arial", 10),
        ).pack(side=tk.LEFT, padx=12)

    def _utworz_okno_wynikow(self):
        if self.okno_wynikow is not None and self.okno_wynikow.winfo_exists():
            return

        self.okno_wynikow = tk.Toplevel(self.root)
        self.okno_wynikow.title("Wyniki - postęp i wykres")
        self.okno_wynikow.geometry("740x780")
        self.okno_wynikow.minsize(640, 600)

        w = tk.Frame(self.okno_wynikow, padx=12, pady=10)
        w.pack(fill=tk.BOTH, expand=True)

        tk.Label(w, text="Postęp obliczeń", font=("Arial", 12, "bold")).pack(anchor="w")

        tk.Label(w, text="Czas:", font=("Arial", 9)).pack(anchor="w", pady=(8, 0))
        self.progress_time = ttk.Progressbar(w, orient="horizontal", length=680, mode="determinate")
        self.progress_time.pack(fill=tk.X, pady=2)
        self.lbl_time = tk.Label(w, text="Czekam na start...", fg="gray", font=("Arial", 9))
        self.lbl_time.pack(anchor="w")

        tk.Label(w, text="Iteracje (najwięcej w jednym wątku):", font=("Arial", 9)).pack(
            anchor="w", pady=(10, 0)
        )
        self.progress_iter = ttk.Progressbar(w, orient="horizontal", length=680, mode="determinate")
        self.progress_iter.pack(fill=tk.X, pady=2)
        self.lbl_iter = tk.Label(w, text="Iteracje: -", fg="gray", font=("Arial", 9))
        self.lbl_iter.pack(anchor="w")

        ttk.Separator(w, orient="horizontal").pack(fill=tk.X, pady=12)

        tk.Label(w, text="Wykres najlepszej długości wyrównania", font=("Arial", 12, "bold")).pack(anchor="w")
        self.fig = Figure(figsize=(6.8, 2.5), dpi=100)
        self.fig.subplots_adjust(left=0.10, right=0.98, top=0.90, bottom=0.24)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_xlabel("Iteracja", labelpad=8)
        self.ax.set_ylabel("Najlepsza długość")
        self.ax.grid(True, linestyle="--", alpha=0.35)
        self.line, = self.ax.plot(
            [], [], color="#1565c0", linewidth=2.0, drawstyle="steps-post", marker="o", markersize=3
        )
        frame_wykres = tk.Frame(w)
        frame_wykres.pack(fill=tk.X, pady=(0, 4))
        self.canvas = FigureCanvasTkAgg(self.fig, master=frame_wykres)
        self.canvas.get_tk_widget().pack(fill=tk.X)
        odstep_pod_wykresem = tk.Frame(frame_wykres, height=1)
        odstep_pod_wykresem.pack(fill=tk.X)
        odstep_pod_wykresem.pack_propagate(False)

        frame_stats = tk.LabelFrame(
            w, text="Podsumowanie najlepszego wyniku", font=("Arial", 10, "bold")
        )
        frame_stats.pack(fill=tk.X, pady=(20, 6))
        self.lbl_stat_dlugosc = tk.Label(frame_stats, text="Długość wyrównania: -", font=("Arial", 10), anchor="w")
        self.lbl_stat_dlugosc.pack(fill=tk.X, padx=8, pady=2)
        self.lbl_stat_konflikty = tk.Label(
            frame_stats, text="Konflikty w kolumnach: -", font=("Arial", 10), anchor="w"
        )
        self.lbl_stat_konflikty.pack(fill=tk.X, padx=8, pady=2)
        self.lbl_stat_czas_cpp = tk.Label(
            frame_stats, text="Czas obliczeń: -", font=("Arial", 10), anchor="w"
        )
        self.lbl_stat_czas_cpp.pack(fill=tk.X, padx=8, pady=2)

        tk.Label(w, text="Macierz wyrównania:", font=("Arial", 10, "bold")).pack(
            anchor="w", pady=(6, 4)
        )
        self.text_out = tk.Text(w, height=8, width=80, font=("Courier", 10), bg="#e8f4f8")
        self.text_out.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.btn_zapisz_raport = tk.Button(
            w, text="Zapisz raport", command=self.zapisz_raport, font=("Arial", 11, "bold")
        )
        self.btn_zapisz_raport.pack(pady=4)

        self.okno_wynikow.protocol("WM_DELETE_WINDOW", self._ukryj_okno_wynikow)
        self.okno_wynikow.withdraw()

    def _pokaz_okno_wynikow(self):
        self._utworz_okno_wynikow()
        self.okno_wynikow.deiconify()
        self.okno_wynikow.lift()
        self.okno_wynikow.focus_force()

    def _ukryj_okno_wynikow(self):
        if self.okno_wynikow and self.okno_wynikow.winfo_exists():
            self.okno_wynikow.withdraw()

    def _zamknij_aplikacje(self):
        if self.is_running:
            if not messagebox.askyesno(
                "Zamykanie",
                "Obliczenia mogą jeszcze działać w tle. Zamknąć program?",
                parent=self.root,
            ):
                return
        if self.okno_wynikow and self.okno_wynikow.winfo_exists():
            self.okno_wynikow.destroy()
        self.root.destroy()

    def _sciezka_silnika_cpp(self):
        for name in ("tabu_search", "zaawansprog", "tabu_search.exe", "zaawansprog.exe"):
            p = os.path.join(self._proj_dir, name)
            if os.path.isfile(p):
                return p
        return None

    def _reset_wykresu(self):
        self._chart_iter.clear()
        self._chart_best.clear()
        self._chart_global_best = None
        self._ostatnia_iteracja = 0
        self.line.set_data([], [])
        self.ax.set_xlim(0, 1)
        self.ax.set_ylim(auto=True)
        self.canvas.draw()

    def _chart_start_od_zera(self, y):
        """pierwszy punkt wykresu od iteracji 0"""
        if self._chart_iter:
            return
        self._chart_global_best = int(y)
        self._chart_iter.append(0)
        self._chart_best.append(self._chart_global_best)

    def _chart_rozszerz_w_prawo(self, iteracja):
        """poziomy odcinek w prawo bez poprawy dlugosci"""
        if self._chart_global_best is None:
            return
        x = int(iteracja)
        if x < 0 or x > self._chart_iter_limit:
            return
        self._ostatnia_iteracja = max(self._ostatnia_iteracja, x)
        if not self._chart_iter:
            self._chart_start_od_zera(self._chart_global_best)
        if not self._chart_iter or x <= self._chart_iter[-1]:
            return
        self._chart_iter.append(x)
        self._chart_best.append(self._chart_global_best)

    def _chart_schodek_w_dol(self, iteracja, nowa_dlugosc):
        """schodek w dol przy nowym rekordzie dlugosci"""
        x = int(iteracja)
        y = int(nowa_dlugosc)
        if x < 0:
            return
        self._ostatnia_iteracja = max(self._ostatnia_iteracja, x)
        if not self._chart_iter:
            self._chart_iter.append(x)
            self._chart_best.append(y)
            return
        lx, ly = self._chart_iter[-1], self._chart_best[-1]
        if x < lx:
            return
        if x == lx:
            self._chart_best[-1] = min(ly, y)
            return
        if y < ly:
            self._chart_iter.append(x)
            self._chart_best.append(ly)
        self._chart_iter.append(x)
        self._chart_best.append(y)

    def _chart_przytnij_do_iteracji(self, iter_koniec):
        while len(self._chart_iter) > 1 and self._chart_iter[-1] > iter_koniec:
            self._chart_iter.pop()
            self._chart_best.pop()
        if self._chart_iter and self._chart_iter[-1] > iter_koniec:
            self._chart_iter[-1] = iter_koniec

    def _chart_ustaw_marginesy_osi(self):
        if not self._chart_iter:
            return
        xmin = min(self._chart_iter)
        xmax = max(self._chart_iter[-1], 1)
        ymin = min(self._chart_best)
        ymax = max(self._chart_best)
        span_x = max(xmax - xmin, 1)
        span_y = max(ymax - ymin, 1)
        pad_x = max(3, int(span_x * self._chart_pad_x_frac))
        pad_y_bot = max(2, int(span_y * self._chart_pad_y_frac))
        pad_y_top = max(2, int(span_y * self._chart_pad_y_frac * 0.5))
        self.ax.set_xlim(xmin - pad_x, xmax + max(3, int(span_x * 0.02)))
        self.ax.set_ylim(ymin - pad_y_bot, ymax + pad_y_top)

    def _chart_rysuj(self):
        if not self._chart_iter:
            return
        self.line.set_data(self._chart_iter, self._chart_best)
        self._chart_ustaw_marginesy_osi()
        self.canvas.draw()

    def aktualizuj_wykres(self, iteracja, najlepsza_dlugosc):
        y = int(najlepsza_dlugosc)
        if self._chart_global_best is None:
            self._chart_start_od_zera(y)
            self._chart_rozszerz_w_prawo(iteracja)
        elif y < self._chart_global_best:
            self._chart_global_best = y
            self._chart_schodek_w_dol(iteracja, y)
        else:
            self._chart_rozszerz_w_prawo(iteracja)
        self._chart_rysuj()

    def generuj(self):
        self.wstrzykniete_bledy = 0
        try:
            m = int(self.entry_m.get())
            n = int(self.entry_n.get())
            d = int(self.entry_d.get())
        except ValueError:
            messagebox.showerror("Błąd", "Wartości m, n i d muszą być liczbami całkowitymi.")
            return
        if m <= 0 or n <= 0 or d <= 0:
            messagebox.showerror("Błąd", "m, n i d muszą być dodatnie.")
            return
        if n > d:
            messagebox.showerror("Błąd", "Musi być n <= d (sekwencja nie może być dłuższa niż nadciąg).")
            return
        if self.combo_alfabet.get().startswith("AC "):
            alfabet = "AC"
        else:
            alfabet = "ACGT"
        nadciag = "".join(random.choices(alfabet, k=d))
        self.text_in.delete("1.0", tk.END)
        sekwencje = []
        for _ in range(m):
            indeksy = sorted(random.sample(range(d), n))
            sek = "".join([nadciag[i] for i in indeksy])
            sekwencje.append(sek)
        random.shuffle(sekwencje)
        for sek in sekwencje:
            self.text_in.insert(tk.END, sek + "\n")
        self.lbl_optimum.config(
            text=f"Zrozumienie optymalności: Znana minimalna długość <= {d} (czysta instancja)",
            fg="green",
        )

    def wyczysc_wzorzec(self):
        self.text_in.delete("1.0", tk.END)
        self.wstrzykniete_bledy = 0
        self.lbl_optimum.config(text="Znane optimum: -", fg="green")

    def wstrzyknij_bledy(self):
        dane = self.text_in.get("1.0", tk.END).strip().split("\n")
        if not dane or not dane[0]:
            return

        try:
            errors = int(self.entry_errors.get())
        except ValueError:
            messagebox.showerror("Błąd", "Podaj poprawną liczbę mutacji.")
            return

        if self.combo_alfabet.get().startswith("AC "):
            alfabet = "AC"
        else:
            alfabet = "ACGT"
        sekwencje_lista = [list(sek) for sek in dane if sek]
        m = len(sekwencje_lista)
        if m == 0:
            return

        for _ in range(errors):
            losowy_wiersz = random.randint(0, m - 1)
            n = len(sekwencje_lista[losowy_wiersz])
            if n == 0:
                continue
            losowa_kolumna = random.randint(0, n - 1)

            stara_litera = sekwencje_lista[losowy_wiersz][losowa_kolumna]

            niedozwolone = {stara_litera}

            if losowa_kolumna > 0:
                niedozwolone.add(sekwencje_lista[losowy_wiersz][losowa_kolumna - 1])

            if losowa_kolumna < n - 1:
                niedozwolone.add(sekwencje_lista[losowy_wiersz][losowa_kolumna + 1])

            dostepne_litery = [c for c in alfabet if c not in niedozwolone]

            if dostepne_litery:
                nowa_litera = random.choice(dostepne_litery)
                sekwencje_lista[losowy_wiersz][losowa_kolumna] = nowa_litera

        self.text_in.delete("1.0", tk.END)
        for sek in sekwencje_lista:
            self.text_in.insert(tk.END, "".join(sek) + "\n")

        self.wstrzykniete_bledy += errors
        try:
            d = int(self.entry_d.get())
        except ValueError:
            d = "?"
        self.lbl_optimum.config(
            text=f"Zrozumienie optymalności: Znana minimalna długość <= {d} (wprowadzono mutacje!)",
            fg="orange",
        )

    def uruchom_cpp(self):
        exe = self._sciezka_silnika_cpp()
        if not exe:
            messagebox.showerror(
                "Błąd",
                "Brak programu zaawansprog (lub tabu_search) w folderze projektu.\n"
                "Zbuduj C++ i skopiuj plik do katalogu z generator_ui.py.",
            )
            return

        linie = [ln.strip() for ln in self.text_in.get("1.0", tk.END).strip().split("\n") if ln.strip()]
        if not linie:
            messagebox.showwarning("Brak danych", "Wpisz lub wygeneruj co najmniej jedną sekwencję.")
            return
        random.shuffle(linie)  # mieszamy kolejnosc przed wyslaniem do c++
        instancja_tresc = "\n".join(linie)

        inst_path = os.path.join(self._proj_dir, "instancja.txt")
        with open(inst_path, "w", encoding="utf-8") as f:
            f.write(instancja_tresc)

        try:
            threads = int(self.entry_threads.get())
            time_limit = int(self.entry_time.get())
            max_iter = int(self.entry_iter.get())
        except ValueError:
            messagebox.showerror("Błąd", "Liczba wątków, limit czasu i limit iteracji muszą być liczbami.")
            return

        self._snapshot_raport = {
            "data_rozpoczecia": datetime.now().isoformat(timespec="seconds"),
            "m": self.entry_m.get().strip(),
            "n": self.entry_n.get().strip(),
            "d": self.entry_d.get().strip(),
            "alfabet": self.combo_alfabet.get(),
            "bledy_mutacji": self.entry_errors.get().strip(),
            "watki": str(threads),
            "czas_max_s": str(time_limit),
            "max_iteracji": str(max_iter),
            "instancja": instancja_tresc,
            "silnik_cpp": exe,
        }

        self._pokaz_okno_wynikow()
        self.btn_run.config(state=tk.DISABLED)

        self.progress_time["maximum"] = time_limit * 10
        self.progress_time["value"] = 0
        self.progress_iter["maximum"] = max_iter
        self.progress_iter["value"] = 0
        self._chart_iter_limit = max_iter
        self._ostatnia_iteracja = 0

        self.is_running = True
        self.text_out.delete("1.0", tk.END)
        self._reset_wykresu()
        self.lbl_time.config(text="Uruchamiam silnik C++...", fg="blue")
        self.lbl_iter.config(text="Iteracje: 0", fg="purple")
        self.lbl_stat_dlugosc.config(text="Długość wyrównania: ...")
        self.lbl_stat_konflikty.config(text="Konflikty w kolumnach: ...")
        self.lbl_stat_czas_cpp.config(text="Czas obliczeń: ...")

        threading.Thread(
            target=self.watek_obliczeniowy,
            args=(exe, threads, time_limit, max_iter),
            daemon=True,
        ).start()

        self.aktualizuj_pasek_czasu()

    def aktualizuj_pasek_czasu(self):
        if self.is_running:
            self.progress_time["value"] += 1
            pozostalo = (self.progress_time["maximum"] - self.progress_time["value"]) / 10.0
            self.lbl_time.config(
                text=f"Trwa obliczanie, zostało do {max(0.0, pozostalo):.1f} s (limit czasu)",
                fg="blue",
            )

            if self.progress_time["value"] < self.progress_time["maximum"]:
                self.root.after(100, self.aktualizuj_pasek_czasu)

    def aktualizuj_pasek_iteracji(self, aktualna_iteracja, najlepsza_dlugosc=None):
        self._ostatnia_iteracja = max(self._ostatnia_iteracja, aktualna_iteracja)
        self.progress_iter["value"] = min(aktualna_iteracja, self.progress_iter["maximum"])
        self.lbl_iter.config(text=f"Iteracje: {aktualna_iteracja} / {self.progress_iter['maximum']}", fg="purple")
        if not self.is_running or najlepsza_dlugosc is None:
            return
        y = int(najlepsza_dlugosc)
        if self._chart_global_best is None:
            self._chart_start_od_zera(y)
            self._chart_rozszerz_w_prawo(aktualna_iteracja)
        elif y < self._chart_global_best:
            self._chart_global_best = y
            self._chart_schodek_w_dol(aktualna_iteracja, y)
        else:
            self._chart_rozszerz_w_prawo(aktualna_iteracja)
        self._chart_rysuj()

    def watek_obliczeniowy(self, exe, threads, time_limit, max_iter):
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"  # zeby progress/chart lecialy na biezaco
            process = subprocess.Popen(
                [exe, str(threads), str(time_limit), str(max_iter)],
                cwd=self._proj_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                env=env,
            )

            for line in process.stdout:
                line_strip = line.strip()
                if line_strip.startswith("PROGRESS:"):  # postep z watku 0
                    try:
                        payload = line_strip.split(":", 1)[1]
                        if "," in payload:
                            it_s, best_s = payload.split(",", 1)
                            current_it = int(it_s)
                            best_len = int(best_s)
                            self.root.after(
                                0, self.aktualizuj_pasek_iteracji, current_it, best_len
                            )
                        else:
                            current_it = int(payload)
                            self.root.after(0, self.aktualizuj_pasek_iteracji, current_it)
                    except ValueError:
                        pass
                elif line_strip.upper().startswith("CHART:"):  # punkt na wykres live
                    m = _RE_CHART.match(line_strip)
                    if m:
                        iteracja = int(m.group(1))
                        najlepsza = int(m.group(2))
                        self.root.after(0, self.aktualizuj_wykres, iteracja, najlepsza)

            process.wait()

            wp = os.path.join(self._proj_dir, "wynik.txt")
            with open(wp, "r", encoding="utf-8", errors="replace") as f:
                wynik = f.read()

            self.root.after(0, self.pokaz_sukces, wynik)

        except Exception as e:
            self.root.after(0, self.pokaz_blad, str(e))

    def pokaz_sukces(self, wynik):
        self.is_running = False
        self.progress_time["value"] = self.progress_time["maximum"]
        self.lbl_time.config(text="Gotowe.", fg="green")

        wp = os.path.join(self._proj_dir, "wynik.txt")
        try:
            with open(wp, "r", encoding="utf-8", errors="replace") as f:
                wynik = f.read()
        except OSError:
            pass

        self._ostatni_wynik_tekst = wynik
        if self._snapshot_raport is not None:
            self._snapshot_raport["data_zakonczenia"] = datetime.now().isoformat(timespec="seconds")

        linie = wynik.splitlines()
        stats = None
        for ln in linie[:20]:
            stats = _parsuj_linie_stats(ln)
            if stats:
                break
        iter_koniec = self._ostatnia_iteracja
        self.progress_iter["value"] = min(iter_koniec, self.progress_iter["maximum"])
        limit_iter = self.progress_iter["maximum"]
        if iter_koniec >= limit_iter:
            self.lbl_iter.config(text=f"Stop: osiągnięto {limit_iter} iteracji", fg="green")
        else:
            self.lbl_iter.config(
                text=f"Stop po {iter_koniec} iteracjach (limit czasu lub wcześniejszy koniec)",
                fg="green",
            )
        if stats:
            self._chart_przytnij_do_iteracji(iter_koniec)
            y = stats["dlugosc"]
            if self._chart_global_best is None or y < self._chart_global_best:
                self._chart_global_best = y
                self._chart_schodek_w_dol(iter_koniec, y)
            else:
                self._chart_rozszerz_w_prawo(iter_koniec)
            self._chart_rysuj()
        if stats:
            self.lbl_stat_dlugosc.config(
                text=f"Długość wyrównania: {stats['dlugosc']}",
                fg="darkgreen",
            )
            self.lbl_stat_konflikty.config(
                text=f"Konflikty w kolumnach: {stats['konflikty']}",
                fg="darkgreen",
            )
            self.lbl_stat_czas_cpp.config(
                text=f"Czas obliczeń: {stats['czas_obliczen']:.4f} s",
                fg="darkgreen",
            )
        else:
            self.lbl_stat_dlugosc.config(text="Długość wyrównania: brak danych (STATS)", fg="gray")
            self.lbl_stat_konflikty.config(text="Konflikty w kolumnach: brak danych", fg="gray")
            self.lbl_stat_czas_cpp.config(text="Czas obliczeń: brak danych", fg="gray")

        self.text_out.delete("1.0", tk.END)
        self.text_out.insert(tk.END, wynik)

        self.btn_run.config(state=tk.NORMAL)
        self._pokaz_okno_wynikow()

    def pokaz_blad(self, blad):
        self.is_running = False
        self.lbl_time.config(text="Błąd silnika C++", fg="red")
        self.lbl_iter.config(text="Przerwano", fg="red")
        messagebox.showerror("Błąd", f"Nie udało się uruchomić obliczeń:\n{blad}")
        self.btn_run.config(state=tk.NORMAL)
        self._pokaz_okno_wynikow()

    def zapisz_raport(self):
        if not self._snapshot_raport:
            messagebox.showwarning("Raport", "Najpierw uruchom obliczenia, żeby mieć co zapisać w raporcie.")
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Plik tekstowy", "*.txt"), ("Wszystkie pliki", "*.*")],
            title="Zapisz raport",
        )
        if not path:
            return

        sn = self._snapshot_raport
        linie = [
            "=" * 72,
            "RAPORT - Problem VII (Tabu Search + UI Python)",
            "=" * 72,
            f"Data zapisu raportu: {datetime.now().isoformat(timespec='seconds')}",
            f"Start obliczen: {sn.get('data_rozpoczecia', '-')}",
            f"Koniec obliczen: {sn.get('data_zakonczenia', '-')}",
            "",
            "--- Parametry generatora ---",
            f"Liczba sekwencji m: {sn['m']}",
            f"Dlugosc sekwencji n: {sn['n']}",
            f"Dlugosc nadciagu d: {sn['d']}",
            f"Alfabet: {sn.get('alfabet', '-')}",
            f"Liczba dodanych mutacji: {self.wstrzykniete_bledy}",
            "",
            "--- Parametry silnika C++ ---",
            f"Program: {sn['silnik_cpp']}",
            f"Watki: {sn['watki']}",
            f"Limit czasu [s]: {sn['czas_max_s']}",
            f"Limit iteracji: {sn['max_iteracji']}",
            "",
            "--- Instancja wejsciowa (instancja.txt) ---",
            sn["instancja"],
            "",
            "--- Plik wynik.txt (ostatnie uruchomienie) ---",
            self._ostatni_wynik_tekst
            if self._ostatni_wynik_tekst
            else "(brak - obliczenia nie zakonczyly sie lub nie odczytano pliku)",
            "",
            "=" * 72,
        ]
        tresc = "\n".join(linie)

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(tresc)
            messagebox.showinfo("Raport", f"Zapisano:\n{path}")
        except OSError as e:
            messagebox.showerror("Błąd zapisu", str(e))


if __name__ == "__main__":
    root = tk.Tk()
    app = TabuSearchUI(root)
    root.mainloop()
