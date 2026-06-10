#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <thread>
#include <mutex>
#include <algorithm>
#include <random>
#include <deque>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cctype>

using namespace std;

static string normalizuj_linie_instancji(const string& l) {
    string out;
    out.reserve(l.size());
    for (unsigned char ch : l) {
        char u = (char)toupper(ch);
        if (u == 'A' || u == 'C' || u == 'G' || u == 'T' || u == '_')
            out.push_back(u);
    }
    return out;
}

enum class TypRuchu : int8_t {
    SwapSasiedni = 0,
    PrzesunBlok = 1,
    UsunPustaKolumne = 2,
    WstawPustaKolumne = 3,
};

struct Rozwiazanie {
    vector<string> sekwencje;
    int funkcja_celu;
};

struct Ruch {
    TypRuchu typ;
    int wiersz;
    int a;
    int b;
    int c;

    bool operator==(const Ruch& inny) const {
        return typ == inny.typ && wiersz == inny.wiersz && a == inny.a && b == inny.b && c == inny.c;
    }
};

static int szerokosc_macierzy(const vector<string>& sekw) {
    int w = 0;
    for (const auto& s : sekw) w = max(w, (int)s.size());
    return w;
}

static bool kolumna_wszystkie_spacje(const vector<string>& sekw, int col) {
    for (const auto& s : sekw) {
        if (col >= (int)s.length()) return false;
        if (s[col] != '_') return false;
    }
    return true;
}

static bool przesun_blok_lewo(vector<string>& sekw, int r, int lo, int hi) {
    if (lo <= 0 || sekw[r][lo - 1] != '_') return false;
    for (int k = lo; k <= hi; ++k)
        if (sekw[r][k] == '_') return false;
    rotate(sekw[r].begin() + (lo - 1), sekw[r].begin() + lo, sekw[r].begin() + (hi + 1));
    return true;
}

static bool przesun_blok_prawo(vector<string>& sekw, int r, int lo, int hi) {
    if (hi + 1 >= (int)sekw[r].length() || sekw[r][hi + 1] != '_') return false;
    for (int k = lo; k <= hi; ++k)
        if (sekw[r][k] == '_') return false;
    rotate(sekw[r].begin() + lo, sekw[r].begin() + (hi + 1), sekw[r].begin() + (hi + 2));
    return true;
}

static void usun_kolumne(vector<string>& sekw, int col) {
    for (auto& s : sekw) {
        if (col < (int)s.length()) s.erase(s.begin() + col);
    }
}

static void wstaw_pusta_kolumne(vector<string>& sekw, int col) {
    for (auto& s : sekw) {
        int pos = min(col, (int)s.length());
        s.insert(s.begin() + pos, '_');
    }
}

static Ruch odwrotnosc_ruchu(const Ruch& u) {
    switch (u.typ) {
    case TypRuchu::SwapSasiedni:
        return u;
    case TypRuchu::PrzesunBlok:
        if (u.c == 0)
            return {TypRuchu::PrzesunBlok, u.wiersz, u.a - 1, u.b - 1, 1};
        return {TypRuchu::PrzesunBlok, u.wiersz, u.a + 1, u.b + 1, 0};
    case TypRuchu::UsunPustaKolumne:
        return {TypRuchu::WstawPustaKolumne, -1, u.a, 0, 0};
    case TypRuchu::WstawPustaKolumne:
        return {TypRuchu::UsunPustaKolumne, -1, u.a, 0, 0};
    default:
        return u;
    }
}

static bool generuj_sasiada_blok(const vector<string>& obecne, mt19937& rng, vector<string>& out, Ruch& prop) {
    int m = (int)obecne.size();
    if (m == 0) return false;
    int r = (int)(rng() % (unsigned)m);
    const string& row = obecne[r];
    if (row.length() < 2) return false;

    int p = (int)(rng() % (unsigned)row.length());
    if (row[p] == '_') {
        int q = p;
        while (q < (int)row.length() && row[q] == '_') ++q;
        if (q == (int)row.length()) return false;
        p = q;
    }

    int lo = p, hi = p;
    while (lo > 0 && row[lo - 1] != '_') --lo;
    while (hi + 1 < (int)row.length() && row[hi + 1] != '_') ++hi;

    out = obecne;
    bool canL = (lo > 0 && out[r][lo - 1] == '_');
    bool canR = (hi + 1 < (int)out[r].length() && out[r][hi + 1] == '_');
    if (!canL && !canR) return false;

    bool goLeft = canL && (!canR || (rng() % 2 == 0));
    if (goLeft) {
        if (!przesun_blok_lewo(out, r, lo, hi)) return false;
        prop = {TypRuchu::PrzesunBlok, r, lo, hi, 0};
        return true;
    }
    if (!przesun_blok_prawo(out, r, lo, hi)) return false;
    prop = {TypRuchu::PrzesunBlok, r, lo, hi, 1};
    return true;
}

static bool generuj_sasiada_gap(const vector<string>& obecne, mt19937& rng, vector<string>& out, Ruch& prop) {
    if (obecne.empty()) return false;
    int W = szerokosc_macierzy(obecne);
    if (W <= 0) return false;

    if (rng() % 2 == 0) {
        vector<int> kandydaci;
        kandydaci.reserve(W);
        for (int c = 0; c < W; ++c) {
            if (kolumna_wszystkie_spacje(obecne, c)) kandydaci.push_back(c);
        }
        if (kandydaci.empty()) return false;
        int c = kandydaci[(int)(rng() % (unsigned)kandydaci.size())];
        out = obecne;
        usun_kolumne(out, c);
        prop = {TypRuchu::UsunPustaKolumne, -1, c, 0, 0};
        return true;
    }

    int pos = (int)(rng() % (unsigned)(W + 1));
    out = obecne;
    wstaw_pusta_kolumne(out, pos);
    prop = {TypRuchu::WstawPustaKolumne, -1, pos, 0, 0};
    return true;
}

Rozwiazanie najlepsze_globalne;
mutex mtx;

const int INF = 999999999;

static inline int indeks_dna(char c) {
    switch (c) {
    case 'A': return 0;
    case 'C': return 1;
    case 'G': return 2;
    case 'T': return 3;
    default: return -1;
    }
}

// ile liter w kolumnie nie zgadza sie z plurality (glos wiekszosciowy)
static int suma_niedopasowan_do_plurality(const vector<string>& sekwencje, int max_dl) {
    int suma = 0;
    int cnt[4];
    for (int col = 0; col < max_dl; ++col) {
        cnt[0] = cnt[1] = cnt[2] = cnt[3] = 0;
        int n = 0;
        for (const auto& sek : sekwencje) {
            if (col >= (int)sek.length()) continue;
            int id = indeks_dna(sek[col]);
            if (id < 0) continue;
            cnt[id]++;
            n++;
        }
        if (n <= 1) continue;
        int mx = max({cnt[0], cnt[1], cnt[2], cnt[3]});
        suma += n - mx;
    }
    return suma;
}

// zwraca dlugosc wyrownania i liczbe konfliktow w kolumnach
pair<int, int> rozklad_oceny(const vector<string>& sekwencje) {
    if (sekwencje.empty()) return {0, 0};
    int max_dl = 0;
    for (const auto& s : sekwencje) {
        int dl_lokalna = 0;
        for (int i = (int)s.length() - 1; i >= 0; i--) {
            if (s[i] != '_') {
                dl_lokalna = i + 1;
                break;
            }
        }
        if (dl_lokalna > max_dl) max_dl = dl_lokalna;
    }
    int suma_nied = suma_niedopasowan_do_plurality(sekwencje, max_dl);
    return {max_dl, suma_nied};
}

int oceniaj(const vector<string>& sekwencje, int waga_konfliktu) {
    if (sekwencje.empty()) return INF;
    auto [max_dl, suma_nied] = rozklad_oceny(sekwencje);
    return max_dl + suma_nied * waga_konfliktu;
}

static int koszt_kolumny_plurality(int col, const vector<string>& sekw) {
    int cnt[4] = {0, 0, 0, 0};
    int n = 0;
    for (const auto& s : sekw) {
        if (col >= (int)s.length()) continue;
        int id = indeks_dna(s[col]);
        if (id < 0) continue;
        cnt[id]++;
        n++;
    }
    if (n <= 1) return 0;
    int mx = max({cnt[0], cnt[1], cnt[2], cnt[3]});
    return n - mx;
}

static int koszt_okna_kolumn(int col_start, int szer_okna, const vector<string>& sekw) {
    int W = 0;
    for (const auto& x : sekw) W = max(W, (int)x.length());
    int suma = 0;
    for (int c = col_start; c < col_start + szer_okna && c < W; ++c) suma += koszt_kolumny_plurality(c, sekw);
    return suma;
}

static bool kolumna_plurality_konflikt(int col, const vector<string>& sekw, char& out_maj) {
    int cnt[4] = {0, 0, 0, 0};
    for (const auto& s : sekw) {
        if (col >= (int)s.length()) continue;
        int id = indeks_dna(s[col]);
        if (id < 0) continue;
        cnt[id]++;
    }
    int suma = cnt[0] + cnt[1] + cnt[2] + cnt[3];
    if (suma <= 1) return false;
    int mx = max({cnt[0], cnt[1], cnt[2], cnt[3]});
    if (suma - mx == 0) return false;
    int bi = -1;
    for (int i = 0; i < 4; ++i) {
        if (cnt[i] == 0) continue;
        if (bi < 0 || cnt[i] > cnt[bi] || (cnt[i] == cnt[bi] && i < bi)) bi = i;
    }
    if (bi < 0) return false;
    out_maj = "ACGT"[bi];
    return true;
}

// heurystyka naprawcza - lookahead po kolumnach
void napraw(vector<string>& sekwencje) {
    if (sekwencje.empty()) return;

    constexpr int LOOKAHEAD_KOLUMN = 8;
    constexpr int MAX_PRZESUNIEC_W_PRAWO = 6;
    const int max_ochrona = max(50000, (int)sekwencje.size() * 5000);

    for (int krok = 0; krok < max_ochrona; ++krok) {
        int szer = szerokosc_macierzy(sekwencje);
        int c_bad = -1;
        char majority = 'A';
        for (int c = 0; c < szer; ++c) {
            if (kolumna_plurality_konflikt(c, sekwencje, majority)) {
                c_bad = c;
                break;
            }
        }
        if (c_bad < 0) break;

        int r_bad = -1;
        for (int r = 0; r < (int)sekwencje.size(); ++r) {
            if (c_bad >= (int)sekwencje[r].length()) continue;
            char ch = sekwencje[r][c_bad];
            if (ch != '_' && ch != majority) {
                r_bad = r;
                break;
            }
        }
        if (r_bad < 0) break;

        int najlepszy_koszt = INF;
        int tryb = 0;
        int ile_swap = 0;

        {
            vector<string> trial = sekwencje;
            trial[r_bad].insert(trial[r_bad].begin() + c_bad, '_');
            int koszt = koszt_okna_kolumn(c_bad, LOOKAHEAD_KOLUMN, trial);
            najlepszy_koszt = koszt;
            tryb = 0;
            ile_swap = 0;
        }

        for (int k = 1; k <= MAX_PRZESUNIEC_W_PRAWO; ++k) {
            vector<string> trial = sekwencje;
            int pos = c_bad;
            bool ok = true;
            for (int i = 0; i < k; ++i) {
                if (pos + 1 >= (int)trial[r_bad].length() || trial[r_bad][pos + 1] != '_') {
                    ok = false;
                    break;
                }
                swap(trial[r_bad][pos], trial[r_bad][pos + 1]);
                ++pos;
            }
            if (!ok) break;
            int koszt = koszt_okna_kolumn(c_bad, LOOKAHEAD_KOLUMN, trial);
            if (koszt < najlepszy_koszt) {
                najlepszy_koszt = koszt;
                tryb = 1;
                ile_swap = k;
            } else if (koszt == najlepszy_koszt && tryb == 0) {
                tryb = 1;
                ile_swap = k;
            }
        }

        if (tryb == 0)
            sekwencje[r_bad].insert(sekwencje[r_bad].begin() + c_bad, '_');
        else {
            int pos = c_bad;
            for (int i = 0; i < ile_swap; ++i) {
                swap(sekwencje[r_bad][pos], sekwencje[r_bad][pos + 1]);
                ++pos;
            }
        }
    }

    // na koniec wyrzucamy kolumny z samymi lukami
    while (true) {
        int W = szerokosc_macierzy(sekwencje);
        int usun = -1;
        for (int c = 0; c < W; ++c) {
            if (kolumna_wszystkie_spacje(sekwencje, c)) {
                usun = c;
                break;
            }
        }
        if (usun < 0) break;
        usun_kolumne(sekwencje, usun);
    }
}

void tabu_search_watek(int id_watku, vector<string> instancja, int time_limit_sec, int max_iteracji) {
    if (instancja.empty()) return;
    mt19937 rng(1337 + id_watku);
    auto start_time = chrono::high_resolution_clock::now();

    auto losuj_start = [&]() {
        vector<string> ob = instancja;
        int max_dl = instancja[0].length() * 2 + 50;
        for(int i = 0; i < (int)ob.size(); i++) {
            string s = "";
            for(char c : ob[i]) {
                s += c;
                if(rng() % 100 < 15) s += string(1 + rng() % 2, '_');
            }
            while((int)s.length() < max_dl) s += "_";
            ob[i] = s;
        }
        return ob;
    };

    vector<string> obecne = losuj_start();
    vector<string> najlepsze_lokalne = obecne;

    vector<string> globalnie_najlepsze_z_watku = obecne;
    int najlepsza_dlugosc_po_naprawie = INF;

    {
        vector<string> start_naprawione = obecne;
        napraw(start_naprawione);
        najlepsza_dlugosc_po_naprawie = rozklad_oceny(start_naprawione).first;
        globalnie_najlepsze_z_watku = start_naprawione;
        cout << "CHART:0," << najlepsza_dlugosc_po_naprawie << '\n' << flush; // start wykresu w gui
    }

    deque<Ruch> lista_tabu;
    int tabu_tenure = 15 + rng() % 10;
    int liczba_sasiadow = 20;
    int licznik_brak_poprawy = 0;

    int WK = 2000;
    int ocena_najlepszego_lokalnego = oceniaj(najlepsze_lokalne, WK);

    for (int iter = 0; iter < max_iteracji; ++iter) {
        // heartbeat - na chwile ignorujemy konflikty zeby scisnac dlugosc
        int nowe_WK = (licznik_brak_poprawy % 100 < 15) ? 1 : 2000;
        if (nowe_WK != WK) {
            WK = nowe_WK;
            ocena_najlepszego_lokalnego = oceniaj(najlepsze_lokalne, WK);
        }

        // postep do gui co 500 iter (tylko watk 0)
        if (id_watku == 0 && iter % 500 == 0) {
            string msg = "PROGRESS:" + to_string(iter) + "\n";
            cout << msg << flush;
        }

        // limit czasu sprawdzamy co 100 iter
        if (iter % 100 == 0) {
            auto now = chrono::high_resolution_clock::now();
            int elapsed = chrono::duration_cast<chrono::seconds>(now - start_time).count();
            if (elapsed >= time_limit_sec) break;
        }

        int najlepszy_wynik_sasiada = INF;
        vector<string> najlepszy_sasiad_stan;
        Ruch wybrany_ruch = {TypRuchu::SwapSasiedni, -1, -1, -1, -1};

        for (int s = 0; s < liczba_sasiadow; ++s) {
            vector<string> kopia = obecne;
            Ruch prop;
            bool ok = (rng() % 2 == 0) ? generuj_sasiada_blok(obecne, rng, kopia, prop)
                                       : generuj_sasiada_gap(obecne, rng, kopia, prop);
            if (!ok) continue;

            bool jest_tabu = false;
            for (auto& t : lista_tabu) if (t == prop) jest_tabu = true;

            int wynik = oceniaj(kopia, WK);

            if (!jest_tabu || wynik < ocena_najlepszego_lokalnego) {
                if (wynik < najlepszy_wynik_sasiada) {
                    najlepszy_wynik_sasiada = wynik;
                    najlepszy_sasiad_stan = kopia;
                    wybrany_ruch = prop;
                }
            }
        }

        if (najlepszy_wynik_sasiada != INF) {
            obecne = najlepszy_sasiad_stan;

            if (najlepszy_wynik_sasiada < ocena_najlepszego_lokalnego) {
                ocena_najlepszego_lokalnego = najlepszy_wynik_sasiada;
                licznik_brak_poprawy = 0;
                najlepsze_lokalne = obecne;

                if (WK > 1) {
                    vector<string> t_naprawione = obecne;
                    napraw(t_naprawione);
                    int faktyczna_dlugosc = rozklad_oceny(t_naprawione).first;

                    if (faktyczna_dlugosc < najlepsza_dlugosc_po_naprawie) {
                        najlepsza_dlugosc_po_naprawie = faktyczna_dlugosc;
                        globalnie_najlepsze_z_watku = t_naprawione;
                        cout << "CHART:" << iter << ',' << najlepsza_dlugosc_po_naprawie << '\n' << flush; // nowy rekord na wykres
                    }
                }
            } else {
                licznik_brak_poprawy++;
            }

            lista_tabu.push_back(odwrotnosc_ruchu(wybrany_ruch)); // tabu na odwrotnosc ruchu
            if ((int)lista_tabu.size() > tabu_tenure) lista_tabu.pop_front();
        } else {
            licznik_brak_poprawy++;
        }

        // kick-move - reset jak utkniemy w minimum lokalnym
        if (licznik_brak_poprawy > 500) {
            obecne = losuj_start();
            lista_tabu.clear();
            licznik_brak_poprawy = 0;
            najlepsze_lokalne = obecne;
            ocena_najlepszego_lokalnego = oceniaj(najlepsze_lokalne, WK);
        }
    }

    Rozwiazanie finalne_watku;
    finalne_watku.sekwencje = globalnie_najlepsze_z_watku;
    if (najlepsza_dlugosc_po_naprawie == INF) {
        napraw(obecne);
        finalne_watku.sekwencje = obecne;
        finalne_watku.funkcja_celu = rozklad_oceny(obecne).first;
    } else {
        finalne_watku.funkcja_celu = najlepsza_dlugosc_po_naprawie;
    }

    lock_guard<mutex> lock(mtx); // multi-start - merge najlepszego watku
    if (finalne_watku.funkcja_celu < najlepsze_globalne.funkcja_celu) {
        najlepsze_globalne = finalne_watku;
    }
}

int main(int argc, char* argv[]) {
    setvbuf(stdout, nullptr, _IOLBF, 0);

    int n_threads = thread::hardware_concurrency();
    if (n_threads <= 0) n_threads = 4;
    int time_limit = 10;
    int max_iter = 50000;

    if (argc >= 4) {
        try {
            n_threads = stoi(argv[1]);
            time_limit = stoi(argv[2]);
            max_iter = stoi(argv[3]);
        } catch (...) {
            cerr << "Nieprawidlowe argumenty; uzywam wartosci domyslnych.\n";
        }
    }

    ifstream f("instancja.txt");
    vector<string> inst;
    string l;
    while (getline(f, l)) {
        string norm = normalizuj_linie_instancji(l);
        if (!norm.empty()) inst.push_back(norm);
    }
    f.close();

    najlepsze_globalne.funkcja_celu = INF;

    if (inst.empty()) {
        ofstream out("wynik.txt");
        out << "Wynik (Cel): Blad - instancja.txt jest pusta!\n";
        out.close();
        return 0;
    }

    auto t_start = chrono::high_resolution_clock::now();
    vector<thread> threads;
    for(int i=0; i<n_threads; ++i) threads.push_back(thread(tabu_search_watek, i, inst, time_limit, max_iter));
    for(auto& t : threads) t.join();
    double czas_obliczen = chrono::duration<double>(chrono::high_resolution_clock::now() - t_start).count();

    auto [dlugosc, konflikty] = rozklad_oceny(najlepsze_globalne.sekwencje);
    
    // przycinamy macierz do faktycznej dlugosci przed zapisem
    for (auto& s : najlepsze_globalne.sekwencje) {
        if ((int)s.length() > dlugosc) {
            s.erase(dlugosc); // obcinamy nadmiar z prawej
        } else while ((int)s.length() < dlugosc) {
            s.push_back('_'); // dopelniamy lukami jak krotsze
        }
    }

    // konsensus kolumnowy, luki nie wchodza do glosowania
    string konsensus = "";
    for (int c = 0; c < dlugosc; ++c) {
        int cnt[4] = {0}; // acgt
        for (const auto& s : najlepsze_globalne.sekwencje) {
            if (c < (int)s.length() && s[c] != '_') {
                int id = indeks_dna(s[c]);
                if (id >= 0) cnt[id]++;
            }
        }
        
        int max_val = 0;
        char best_char = '_'; // jak w kolumnie same luki
        for (int i = 0; i < 4; ++i) {
            if (cnt[i] > max_val) {
                max_val = cnt[i];
                best_char = "ACGT"[i];
            }
        }
        konsensus += best_char;
    }

    // zapis wynik.txt + twarda ocena (inf jak sa konflikty)
    ofstream out("wynik.txt");
    out << "STATS: Dlugosc=[" << dlugosc << "], LiczbaKonfliktow=[" << konflikty
        << "], CzasObliczen=[" << czas_obliczen << "] s\n";
    if (konflikty == 0)
        out << "Wynik (Cel): " << najlepsze_globalne.funkcja_celu << "\n\n";
    else
        out << "Wynik (Cel): INF (Rozwiązanie niedopuszczalne - zawiera konflikty!)\n\n";
    out << "Sekwencja konsensusowa: " << konsensus << "\n\n";
    
    for(auto& s : najlepsze_globalne.sekwencje) {
        out << s << "\n";
    }
    out.close();

    return 0;
}