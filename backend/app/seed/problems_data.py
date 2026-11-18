"""Original seed problems (Kazakh). Tests are produced by the reference solution inside each
`case` function, so expected outputs always agree with the code.

Each problem: 2 subtasks (small 40 pts / large 60 pts), 3 tests each; the first small test
is the public example. `collection` is kept for the archive module (collections CRUD).
"""

import heapq
import math
import random
from bisect import bisect_left
from collections import Counter, deque
from functools import cmp_to_key, reduce

from app.modules.problems.schemas import HintIn, ProblemIn, SubtaskIn, TestIn, TranslationIn

MOD = 10**9 + 7

COLLECTIONS = [
    "Бастапқы есептер",
    "Сұрыптау және екілік іздеу",
    "Рекурсия және жолдар",
    "Динамикалық бағдарламалау",
    "Графтар",
    "Математика және сандар теориясы",
    "Ашкөз алгоритмдер",
]

_REGISTRY: list[dict] = []


def L(*lines) -> str:
    return "\n".join(str(x) for x in lines) + "\n"


def J(a) -> str:
    return " ".join(map(str, a))


def problem(title, tags, rating, coll, desc, inp, out, hints):
    def deco(fn):
        _REGISTRY.append(
            dict(title=title, tags=tags, rating=rating, collection=COLLECTIONS[coll],
                 desc=desc, inp=inp, out=out, hints=hints, case=fn)
        )
        return fn

    return deco


# ============================ 1. Бастапқы есептер ============================


@problem("Жұп сандардың қосындысы", ["math"], 800, 0,
         "$n$ бүтін сан берілген. Олардың ішіндегі жұп сандардың қосындысын табыңыз.",
         "Бірінші жолда $n$ ($1 \\le n \\le 200$). Екінші жолда $n$ бүтін сан, модулі $10^4$-тен аспайды.",
         "Жұп сандардың қосындысын шығарыңыз (жұп сан болмаса $0$).",
         ("Әр санның жұп екенін тексеріп, тек жұптарын қосыңыз.",
          "Алгоритм: сызықтық өту және $x \\bmod 2 = 0$ шарты.",
          "s = 0; әр x үшін: егер x % 2 == 0 болса, s += x; s шығару"))
def _(r, big):
    n = r.randint(50, 200) if big else r.randint(3, 8)
    a = [r.randint(-10**4, 10**4) if big else r.randint(1, 20) for _ in range(n)]
    return L(n, J(a)), L(sum(x for x in a if x % 2 == 0))


@problem("Айырма", ["sorting"], 800, 0,
         "$n$ бүтін сан берілген. Ең үлкен және ең кіші сандардың айырмасын табыңыз.",
         "Бірінші жолда $n$ ($1 \\le n \\le 10^5$). Екінші жолда $n$ бүтін сан, модулі $10^9$-дан аспайды.",
         "$\\max - \\min$ мәнін шығарыңыз.",
         ("Ең үлкен және ең кіші элементтерді табу жеткілікті.",
          "Алгоритм: сызықтық өту (сұрыптау міндетті емес, бірақ сұрыптап та шешуге болады).",
          "mx = a[0]; mn = a[0]; әр x үшін mx, mn жаңарту; mx - mn шығару"))
def _(r, big):
    n = r.randint(1000, 5000) if big else r.randint(2, 7)
    a = [r.randint(-10**9, 10**9) if big else r.randint(-20, 20) for _ in range(n)]
    return L(n, J(a)), L(max(a) - min(a))


@problem("Тиындар", ["greedy"], 900, 0,
         "Қолда $1, 5, 10, 50, 100$ теңгелік монеталар шексіз көп. $n$ теңгені ең аз монета санымен төлеңіз.",
         "Бір жолда $n$ ($1 \\le n \\le 10^9$).",
         "Ең аз монета санын шығарыңыз.",
         ("Ең үлкен номиналдан бастап алуға тырысыңыз.",
          "Алгоритм: ашкөз алгоритм (номиналдар еселі болғандықтан дұрыс жұмыс істейді).",
          "ans = 0; номиналдарды кему ретімен: ans += n // c; n %= c; ans шығару"))
def _(r, big):
    n = r.randint(10**8, 10**9) if big else r.randint(1, 300)
    m, ans = n, 0
    for c in (100, 50, 10, 5, 1):
        ans += m // c
        m %= c
    return L(n), L(ans)


@problem("Бөлгіштер саны", ["math"], 1000, 0,
         "$n$ санының натурал бөлгіштерінің санын табыңыз.",
         "Бір жолда $n$ ($1 \\le n \\le 10^9$).",
         "Бөлгіштер санын шығарыңыз.",
         ("Бөлгіштер $\\sqrt{n}$ дейін жұп-жұбымен кездеседі.",
          "Алгоритм: $i$ бойынша $1$-ден $\\sqrt{n}$-ге дейін тексеру.",
          "i = 1; i*i <= n болғанда: егер n % i == 0: i*i == n болса +1, әйтпесе +2; i++"))
def _(r, big):
    n = r.choice([735134400, 999999937, 10**9, r.randint(10**8, 10**9)]) if big else r.randint(1, 100)
    c, i = 0, 1
    while i * i <= n:
        if n % i == 0:
            c += 1 if i * i == n else 2
        i += 1
    return L(n), L(c)


@problem("Ортақ бөлгіш", ["math"], 1000, 0,
         "$n$ натурал санның ең үлкен ортақ бөлгішін (ЕҮОБ) табыңыз.",
         "Бірінші жолда $n$ ($1 \\le n \\le 1000$). Екінші жолда $n$ сан, әрқайсысы $1$-ден $10^9$-ға дейін.",
         "ЕҮОБ мәнін шығарыңыз.",
         ("Екі санның ЕҮОБ-ын тауып, оны келесі санмен біріктіріңіз.",
          "Алгоритм: Евклид алгоритмі, $\\gcd(a,b)=\\gcd(b,a \\bmod b)$.",
          "g = a[0]; әр x үшін g = gcd(g, x); gcd(a, b): b == 0 болса a, әйтпесе gcd(b, a % b)"))
def _(r, big):
    n = r.randint(100, 1000) if big else r.randint(2, 5)
    k = r.randint(1, 5000) if big else r.randint(1, 6)
    a = [k * r.randint(1, (10**9 // k) if big else 20) for _ in range(n)]
    return L(n, J(a)), L(reduce(math.gcd, a))


@problem("Жай сандар", ["math"], 1200, 0,
         "$1$-ден $n$-ге дейінгі жай сандардың санын табыңыз.",
         "Бір жолда $n$ ($1 \\le n \\le 10^6$).",
         "Жай сандар санын шығарыңыз.",
         ("Әр санды жеке тексеру баяу; көбейтінділерін сызып тастаңыз.",
          "Алгоритм: Эратосфен електі.",
          "is[2..n] = true; p = 2..n үшін: егер is[p]: j = p*p, p*p+p, ... үшін is[j] = false; is[p] санын есептеу"))
def _(r, big):
    n = r.randint(10**5, 10**6) if big else r.randint(2, 60)
    s = bytearray([1]) * (n + 1)
    s[0:2] = b"\x00\x00"
    for p in range(2, int(n**0.5) + 1):
        if s[p]:
            s[p * p::p] = bytearray(len(s[p * p::p]))
    return L(n), L(sum(s))


@problem("Іс-шаралар кестесі", ["greedy", "sorting"], 1300, 0,
         "Залда $n$ іс-шара өтпек, $i$-ші іс-шара $[l_i, r_i]$ кесіндісінде өтеді. Екі іс-шараның ортақ "
         "уақыт нүктесі болмауы керек. Өткізуге болатын іс-шаралардың ең көп санын табыңыз.",
         "Бірінші жолда $n$ ($1 \\le n \\le 10^5$). Келесі $n$ жолда $l_i, r_i$ ($1 \\le l_i \\le r_i \\le 10^9$).",
         "Ең көп іс-шара санын шығарыңыз.",
         ("Қай іс-шараны бірінші таңдау келесілерге ең көп орын қалдырады?",
          "Алгоритм: аяқталу уақыты бойынша сұрыптап, ашкөз таңдау.",
          "r бойынша сұрыптау; last = -1; әр (l, r) үшін: егер l > last: ans++, last = r"))
def _(r, big):
    n = r.randint(500, 3000) if big else r.randint(3, 7)
    hi = 10**6 if big else 15
    iv = []
    for _ in range(n):
        l = r.randint(1, hi)
        iv.append((l, min(hi, l + r.randint(0, hi // 50 if big else 4))))
    last, ans = -1, 0
    for l, rr in sorted(iv, key=lambda x: (x[1], x[0])):
        if l > last:
            ans += 1
            last = rr
    return L(n, *[f"{l} {rr}" for l, rr in iv]), L(ans)


# ======================= 2. Сұрыптау және екілік іздеу =======================


@problem("Сұрыптау", ["sorting"], 800, 1,
         "$n$ бүтін санды өсу ретімен сұрыптаңыз.",
         "Бірінші жолда $n$ ($1 \\le n \\le 10^5$). Екінші жолда $n$ бүтін сан, модулі $10^9$-дан аспайды.",
         "Сұрыпталған сандарды бос орынмен бөліп шығарыңыз.",
         ("Дайын сұрыптау функциясын қолдануға болады.",
          "Алгоритм: біріктіру арқылы сұрыптау немесе жылдам сұрыптау, $O(n \\log n)$.",
          "a.sort(); a шығару"))
def _(r, big):
    n = r.randint(2000, 8000) if big else r.randint(3, 8)
    a = [r.randint(-10**9, 10**9) if big else r.randint(-9, 9) for _ in range(n)]
    return L(n, J(a)), L(J(sorted(a)))


@problem("Қосындысы берілген жұптар", ["sorting", "math"], 1200, 1,
         "$n$ санның ішінен $i<j$ және $a_i + a_j = S$ болатын $(i, j)$ жұптарының санын табыңыз.",
         "Бірінші жолда $n$ және $S$ ($1 \\le n \\le 2000$). Екінші жолда $n$ бүтін сан, $|a_i| \\le 10^9$.",
         "Жұптар санын шығарыңыз.",
         ("Әр $a_i$ үшін оған қажетті $S - a_i$ санын қанша рет кездесетінін санаңыз.",
          "Алгоритм: сұрыптау + екі нұсқауыш немесе санауыш (хэш-кесте).",
          "cnt = санауыш; әр x үшін y = S - x; x < y: cnt[x]*cnt[y]; x == y: cnt[x]*(cnt[x]-1)/2"))
def _(r, big):
    n = r.randint(500, 2000) if big else r.randint(4, 8)
    hi = 40 if big else 6
    a = [r.randint(1, hi) for _ in range(n)]
    s = r.randint(hi, 2 * hi - 2)
    cnt, res = Counter(a), 0
    for x in cnt:
        y = s - x
        if y in cnt:
            if x < y:
                res += cnt[x] * cnt[y]
            elif x == y:
                res += cnt[x] * (cnt[x] - 1) // 2
    return L(f"{n} {s}", J(a)), L(res)


@problem("Әртүрлі сандар", ["sorting"], 900, 1,
         "$n$ санның ішінде неше әртүрлі мән бар?",
         "Бірінші жолда $n$ ($1 \\le n \\le 10^5$). Екінші жолда $n$ бүтін сан, $|a_i| \\le 10^9$.",
         "Әртүрлі мәндер санын шығарыңыз.",
         ("Сұрыптағаннан кейін бірдей сандар қатар тұрады.",
          "Алгоритм: сұрыптап, көршілерін салыстыру (немесе жиын).",
          "a.sort(); ans = 1; i = 1..n-1 үшін: егер a[i] != a[i-1]: ans++"))
def _(r, big):
    n = r.randint(2000, 8000) if big else r.randint(3, 9)
    hi = 3000 if big else 5
    a = [r.randint(-hi, hi) for _ in range(n)]
    return L(n, J(a)), L(len(set(a)))


@problem("Бар ма?", ["binary-search"], 1000, 1,
         "Өсу ретімен сұрыпталған $n$ сан және $q$ сұраныс берілген. Әр сұраныста $x$ санының массивте бар-жоғын айтыңыз.",
         "Бірінші жолда $n, q$ ($1 \\le n, q \\le 10^5$). Екінші жолда $n$ сан (өсу ретімен сұрыпталған). "
         "Үшінші жолда $q$ сан $x$. Барлық сан модулі бойынша $10^9$-дан аспайды.",
         "Әр сұраныс үшін жеке жолға `YES` немесе `NO` шығарыңыз.",
         ("Массив сұрыпталған, әр қадамда іздеу аймағын жартылай қысқартуға болады.",
          "Алгоритм: екілік іздеу, $O(\\log n)$.",
          "lo = 0; hi = n - 1; lo <= hi болғанда: mid = (lo + hi) / 2; a[mid] == x болса YES; a[mid] < x болса lo = mid + 1; әйтпесе hi = mid - 1"))
def _(r, big):
    n = r.randint(1000, 5000) if big else r.randint(3, 8)
    q = r.randint(1000, 5000) if big else r.randint(3, 6)
    hi = 10**6 if big else 15
    a = sorted(r.randint(-hi, hi) for _ in range(n))
    qs = [r.randint(-hi, hi) for _ in range(q)]
    s = set(a)
    return L(f"{n} {q}", J(a), J(qs)), L(*["YES" if x in s else "NO" for x in qs])


@problem("Бірінші үлкен немесе тең", ["binary-search"], 1300, 1,
         "Өсу ретімен сұрыпталған $n$ сан және $q$ сұраныс берілген. Әр сұраныс үшін $a_i \\ge x$ болатын "
         "ең кіші $i$ индексін ($1$-ден нөмірлегенде) табыңыз; ондай жоқ болса $n+1$ шығарыңыз.",
         "Бірінші жолда $n, q$ ($1 \\le n, q \\le 10^5$). Екінші жолда $n$ сұрыпталған сан. "
         "Үшінші жолда $q$ сан. Барлығы модулі бойынша $10^9$-дан аспайды.",
         "Әр сұраныс үшін жеке жолға жауап шығарыңыз.",
         ("Шарт ($a_i \\ge x$) солдан оңға қарай жалғандан ақиқатқа ауысады.",
          "Алгоритм: екілік іздеу (lower bound).",
          "lo = 0; hi = n; lo < hi болғанда: mid = (lo + hi) / 2; a[mid] >= x болса hi = mid; әйтпесе lo = mid + 1; lo + 1 шығару"))
def _(r, big):
    n = r.randint(1000, 5000) if big else r.randint(3, 8)
    q = r.randint(1000, 5000) if big else r.randint(3, 6)
    hi = 10**6 if big else 15
    a = sorted(r.randint(-hi, hi) for _ in range(n))
    qs = [r.randint(-hi - 2, hi + 2) for _ in range(q)]
    return L(f"{n} {q}", J(a), J(qs)), L(*[bisect_left(a, x) + 1 for x in qs])


@problem("Ағаш кесу", ["binary-search"], 1500, 1,
         "$n$ ағаш діңі бар, ұзындықтары $a_i$. Оларды бүтін ұзындықты тең бөліктерге кесіп, кемінде $k$ бөлік алу керек. "
         "Бөліктің мүмкін болатын ең үлкен ұзындығын табыңыз (мүмкін болмаса $0$).",
         "Бірінші жолда $n, k$ ($1 \\le n \\le 10^5$, $1 \\le k \\le 10^9$). Екінші жолда $n$ сан ($1 \\le a_i \\le 10^9$).",
         "Ең үлкен ұзындықты шығарыңыз.",
         ("Ұзындық өскен сайын бөліктер саны кемиді — бұл монотонды.",
          "Алгоритм: жауап бойынша екілік іздеу.",
          "lo = 0; hi = max(a); lo < hi болғанда: mid = (lo + hi + 1) / 2; sum(a_i / mid) >= k болса lo = mid, әйтпесе hi = mid - 1; lo шығару"))
def _(r, big):
    n = r.randint(500, 3000) if big else r.randint(2, 5)
    hi = 10**9 if big else 30
    a = [r.randint(1, hi) for _ in range(n)]
    k = r.randint(1, 10**5 if big else 12)
    lo, h = 0, max(a)
    while lo < h:
        mid = (lo + h + 1) // 2
        if sum(x // mid for x in a) >= k:
            lo = mid
        else:
            h = mid - 1
    return L(f"{n} {k}", J(a)), L(lo)


def _count_inv(a):
    if len(a) < 2:
        return a, 0
    m = len(a) // 2
    x, cx = _count_inv(a[:m])
    y, cy = _count_inv(a[m:])
    res, i, j, c = [], 0, 0, cx + cy
    while i < len(x) and j < len(y):
        if x[i] <= y[j]:
            res.append(x[i]); i += 1
        else:
            res.append(y[j]); j += 1
            c += len(x) - i
    res += x[i:] + y[j:]
    return res, c


@problem("Инверсиялар", ["sorting", "recursion"], 1800, 1,
         "Массивтегі инверсия — $i<j$ және $a_i>a_j$ болатын $(i,j)$ жұбы. Инверсиялар санын табыңыз.",
         "Бірінші жолда $n$ ($1 \\le n \\le 10^5$). Екінші жолда $n$ бүтін сан, $|a_i| \\le 10^9$.",
         "Инверсиялар санын шығарыңыз.",
         ("Тура санау $O(n^2)$ — тым баяу. Сұрыптау кезінде санауға болады.",
          "Алгоритм: біріктіру арқылы сұрыптау, біріктіру кезінде инверсияларды санау.",
          "Біріктіруде: егер оң жақтағы элемент сол жақтағыдан кіші алынса, ans += сол жақта қалған элементтер саны"))
def _(r, big):
    n = r.randint(10000, 20000) if big else r.randint(3, 8)
    a = [r.randint(-10**9, 10**9) if big else r.randint(1, 9) for _ in range(n)]
    return L(n, J(a)), L(_count_inv(a)[1])


# ========================= 3. Рекурсия және жолдар ==========================


@problem("Факториал", ["recursion", "math"], 800, 2,
         "$n! = 1 \\cdot 2 \\cdots n$ мәнін табыңыз ($0! = 1$).",
         "Бір жолда $n$ ($0 \\le n \\le 20$).",
         "$n!$ мәнін шығарыңыз.",
         ("$n! = n \\cdot (n-1)!$ қатынасын пайдаланыңыз.",
          "Алгоритм: рекурсия (база: $n = 0$).",
          "f(n): егер n == 0: 1 қайтару; әйтпесе n * f(n - 1) қайтару"))
def _(r, big):
    n = r.randint(12, 20) if big else r.randint(0, 8)
    return L(n), L(math.factorial(n))


@problem("Ханой мұнарасы", ["recursion", "math"], 1000, 2,
         "Ханой мұнарасында $n$ диск бар. Барлық дискіні бір стерженьнен екіншісіне көшіру үшін қажет "
         "қадамдардың ең аз санын табыңыз (үлкен диск кішісінің үстіне қойылмайды, бір қадамда бір диск көшіріледі).",
         "Бір жолда $n$ ($1 \\le n \\le 60$).",
         "Қадамдар санын шығарыңыз.",
         ("$n-1$ дискіні қосалқы стерженьге, ең үлкенін көшіріп, қайта $n-1$ дискіні үстіне қою керек.",
          "Алгоритм: рекурсия, $T(n) = 2T(n-1) + 1$.",
          "T(n): егер n == 1: 1; әйтпесе 2 * T(n - 1) + 1. Жабық формула: 2^n - 1"))
def _(r, big):
    n = r.randint(30, 60) if big else r.randint(1, 10)
    return L(n), L(2**n - 1)


@problem("Ішкі жиын қосындысы", ["recursion"], 1300, 2,
         "$n$ натурал сан берілген. Олардың бір бөлігін (бос емес болуы міндетті емес) таңдап, қосындысын "
         "дәл $S$ етуге бола ма?",
         "Бірінші жолда $n$ және $S$ ($1 \\le n \\le 20$, $0 \\le S \\le 10^6$). Екінші жолда $n$ сан ($1 \\le a_i \\le 10^5$).",
         "Болса `YES`, әйтпесе `NO` шығарыңыз.",
         ("Әр сан үшін екі таңдау бар: алу немесе алмау.",
          "Алгоритм: рекурсивті іздеу (толық аралау), $O(2^n)$.",
          "go(i, s): s == S болса YES; i == n болса NO; go(i+1, s + a[i]) немесе go(i+1, s)"))
def _(r, big):
    n = r.randint(14, 20) if big else r.randint(3, 6)
    a = [r.randint(1, 10**5 if big else 9) for _ in range(n)]
    sums = {0}
    for x in a:
        sums |= {s + x for s in sums}
    pool = sorted(sums)
    s = r.choice(pool) if r.random() < 0.5 else r.randint(0, sum(a) + 2)
    return L(f"{n} {s}", J(a)), L("YES" if s in sums else "NO")


@problem("Палиндром", ["strings"], 800, 2,
         "Жол солдан оңға да, оңнан солға да бірдей оқылса, ол палиндром деп аталады. Берілген жол палиндром ма?",
         "Бір жолда кіші латын әріптерінен тұратын жол, ұзындығы $1$-ден $10^5$-ке дейін.",
         "Палиндром болса `YES`, әйтпесе `NO` шығарыңыз.",
         ("Жолдың басы мен соңын салыстырыңыз.",
          "Алгоритм: екі нұсқауыш.",
          "i = 0; j = n - 1; i < j болғанда: s[i] != s[j] болса NO; i++, j--; YES"))
def _(r, big):
    m = r.randint(20000, 50000) if big else r.randint(1, 5)
    h = "".join(r.choice("abc") for _ in range(m))
    s = h + h[::-1][r.randint(0, 1):]
    if r.random() < 0.5:
        i = r.randrange(len(s))
        s = s[:i] + ("a" if s[i] != "a" else "b") + s[i + 1:]
    return L(s), L("YES" if s == s[::-1] else "NO")


@problem("Анаграмма", ["strings", "sorting"], 900, 2,
         "Екі жолдың әріптерін ауыстырып, біреуінен екіншісін алуға болса, олар анаграмма деп аталады.",
         "Екі жолда кіші латын әріптерінен тұратын $s$ және $t$ жолдары, ұзындығы $10^5$-тен аспайды.",
         "Анаграмма болса `YES`, әйтпесе `NO` шығарыңыз.",
         ("Әріптердің орны емес, саны маңызды.",
          "Алгоритм: әріптерді санау немесе екі жолды сұрыптау.",
          "cnt[26] массиві: s үшін +1, t үшін -1; барлығы 0 болса YES"))
def _(r, big):
    m = r.randint(5000, 30000) if big else r.randint(2, 6)
    s = "".join(r.choice("abcd") for _ in range(m))
    t = list(s)
    r.shuffle(t)
    if r.random() < 0.5:
        i = r.randrange(m)
        t[i] = "e"
    t = "".join(t)
    return L(s, t), L("YES" if sorted(s) == sorted(t) else "NO")


@problem("Ортақ префикс", ["strings"], 1000, 2,
         "$n$ жолдың ең ұзын ортақ префиксінің ұзындығын табыңыз.",
         "Бірінші жолда $n$ ($1 \\le n \\le 1000$). Келесі $n$ жолда кіші латын әріптерінен тұратын жолдар, "
         "әрқайсысының ұзындығы $1$-ден $1000$-ға дейін.",
         "Ұзындықты шығарыңыз (ортақ префикс жоқ болса $0$).",
         ("Префикс бірінші жолдың басынан басталады.",
          "Алгоритм: бірінші жолмен әр жолды символ-символмен салыстыру.",
          "ans = len(s[0]); әр жол үшін: ортақ бөлік ұзындығын тауып, ans = min(ans, ұзындық)"))
def _(r, big):
    n = r.randint(100, 1000) if big else r.randint(2, 5)
    base = "".join(r.choice("ab") for _ in range(r.randint(0, 400 if big else 4)))
    ss = [base + "".join(r.choice("ab") for _ in range(r.randint(1, 500 if big else 3))) for _ in range(n)]
    ans = len(ss[0])
    for s in ss[1:]:
        k = 0
        while k < min(len(s), ans) and s[k] == ss[0][k]:
            k += 1
        ans = k
    return L(n, *ss), L(ans)


@problem("Жолды сығу", ["strings"], 1100, 2,
         "Жолды сығудың жолы: қатар тұрған бірдей әріптер тобын «әріп + топтың ұзындығы» деп жазу. "
         "Мысалы, `aaabcc` → `a3b1c2`. Берілген жолды сығыңыз.",
         "Бір жолда кіші латын әріптерінен тұратын жол, ұзындығы $1$-ден $10^5$-ке дейін.",
         "Сығылған жолды шығарыңыз.",
         ("Жолды бойлай өтіп, әр топтың аяқталатын жерін табыңыз.",
          "Алгоритм: екі нұсқауышты қолданып топтау.",
          "i = 0; i < n болғанда: j = i; s[j] == s[i] болғанда j++; шығару s[i] + (j - i); i = j"))
def _(r, big):
    parts = r.randint(2000, 8000) if big else r.randint(2, 5)
    s = "".join(r.choice("abc") * r.randint(1, 6) for _ in range(parts))
    out, i = [], 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        out.append(f"{s[i]}{j - i}")
        i = j
    return L(s), L("".join(out))


def _gen_br(r, m):
    pairs = {"(": ")", "[": "]", "{": "}"}
    s, st, opens = [], [], m
    while opens > 0 or st:
        if opens > 0 and (not st or r.random() < 0.5):
            c = r.choice("([{")
            s.append(c)
            st.append(pairs[c])
            opens -= 1
        else:
            s.append(st.pop())
    return "".join(s)


@problem("Жақшалар тізбегі", ["strings"], 1200, 2,
         "Жақшалар тізбегі дұрыс болуы үшін әр ашылған жақша өзімен түрі бірдей жақшамен дұрыс ретпен жабылуы тиіс. "
         "Мысалы, `([]{})` — дұрыс, `([)]` — бұрыс. Тізбекті тексеріңіз.",
         "Бір жолда `(`, `)`, `[`, `]`, `{`, `}` таңбаларынан тұратын жол, ұзындығы $1$-ден $10^5$-ке дейін.",
         "Дұрыс болса `YES`, әйтпесе `NO` шығарыңыз.",
         ("Соңғы ашылған жақша бірінші болып жабылуы керек.",
          "Алгоритм: стек.",
          "Ашылатын жақшаны стекке салу; жабылатын кезде стектің басы сәйкес болмаса NO; соңында стек бос болса YES"))
def _(r, big):
    m = r.randint(5000, 20000) if big else r.randint(1, 4)
    s = _gen_br(r, m)
    if r.random() < 0.6:
        i = r.randrange(len(s))
        s = s[:i] + r.choice("()[]{}") + s[i + 1:]
    st, ok = [], True
    pairs = {")": "(", "]": "[", "}": "{"}
    for c in s:
        if c in "([{":
            st.append(c)
        elif not st or st.pop() != pairs[c]:
            ok = False
            break
    return L(s), L("YES" if ok and not st else "NO")


@problem("Ең ұзын палиндромдық ішкі жол", ["strings", "dp"], 1700, 2,
         "Жолдың ең ұзын палиндром болатын үзіліссіз ішкі бөлігінің ұзындығын табыңыз.",
         "Бір жолда кіші латын әріптерінен тұратын жол, ұзындығы $1$-ден $2000$-ға дейін.",
         "Ұзындықты шығарыңыз.",
         ("Әр палиндромның бір ортасы бар — ортадан екі жаққа ұзартыңыз.",
          "Алгоритм: центрден кеңейту, $O(n^2)$.",
          "Әр i үшін (i, i) және (i, i+1) орталарынан: s[l] == s[r] болғанда l--, r++; ең үлкен r - l - 1"))
def _(r, big):
    n = r.randint(800, 2000) if big else r.randint(3, 9)
    s = "".join(r.choice("ab" if big else "abc") for _ in range(n))
    best = 1
    for c in range(n):
        for l, rr in ((c, c), (c, c + 1)):
            while l >= 0 and rr < n and s[l] == s[rr]:
                l -= 1
                rr += 1
            best = max(best, rr - l - 1)
    return L(s), L(best)


# ====================== 4. Динамикалық бағдарламалау =========================


@problem("Баспалдақ", ["dp"], 1000, 3,
         "Баспалдақта $n$ сатыр бар. Бір қадамда $1$, $2$ немесе $3$ сатыға көтерілуге болады. "
         "Төбеге неше тәсілмен жетуге болады? Жауапты $10^9+7$ модулімен шығарыңыз.",
         "Бір жолда $n$ ($1 \\le n \\le 10^5$).",
         "Тәсілдер санын $10^9+7$ бойынша қалдықпен шығарыңыз.",
         ("Соңғы қадам қандай болғанын қарастырыңыз.",
          "Алгоритм: динамикалық бағдарламалау, $f(i) = f(i-1) + f(i-2) + f(i-3)$.",
          "f[0] = 1; i = 1..n үшін f[i] = f[i-1] + f[i-2] + f[i-3] (теріс индекс 0), mod 1e9+7"))
def _(r, big):
    n = r.randint(50000, 100000) if big else r.randint(1, 12)
    f = [1] + [0] * n
    for i in range(1, n + 1):
        f[i] = sum(f[i - k] for k in (1, 2, 3) if i - k >= 0) % MOD
    return L(n), L(f[n])


@problem("Рюкзак", ["dp"], 1500, 3,
         "Рюкзактың сыйымдылығы $W$. $n$ зат бар, $i$-ші заттың салмағы $w_i$, құны $v_i$. "
         "Әр затты ең көбі бір рет алып, салмағы $W$-дан аспайтын ең үлкен жалпы құнды табыңыз.",
         "Бірінші жолда $n, W$ ($1 \\le n \\le 100$, $1 \\le W \\le 1000$). Келесі $n$ жолда $w_i, v_i$ ($1 \\le w_i \\le W$, $1 \\le v_i \\le 10^6$).",
         "Ең үлкен жалпы құнды шығарыңыз.",
         ("Әр зат үшін: аламыз немесе алмаймыз.",
          "Алгоритм: 0/1 рюкзак, $dp[j]$ — $j$ салмақпен алынатын ең жақсы құн.",
          "әр зат үшін j = W..w төмен қарай: dp[j] = max(dp[j], dp[j - w] + v)"))
def _(r, big):
    n = r.randint(60, 100) if big else r.randint(2, 5)
    W = r.randint(500, 1000) if big else r.randint(5, 15)
    items = [(r.randint(1, W // 4 if big else 8), r.randint(1, 10**6 if big else 20)) for _ in range(n)]
    dp = [0] * (W + 1)
    for w, v in items:
        for j in range(W, w - 1, -1):
            dp[j] = max(dp[j], dp[j - w] + v)
    return L(f"{n} {W}", *[f"{w} {v}" for w, v in items]), L(max(dp))


@problem("Ең ұзын өспелі тізбек", ["dp", "binary-search"], 1600, 3,
         "$n$ санның ең ұзын қатаң өспелі ішкі тізбегінің (элементтерді өшіріп алуға болады, ретін өзгертуге болмайды) ұзындығын табыңыз.",
         "Бірінші жолда $n$ ($1 \\le n \\le 10^5$). Екінші жолда $n$ бүтін сан, $|a_i| \\le 10^9$.",
         "Ұзындықты шығарыңыз.",
         ("$O(n^2)$ шешім бар, бірақ жылдамырақ мүмкін.",
          "Алгоритм: динамикалық бағдарламалау + екілік іздеу, $O(n \\log n)$.",
          "t = []; әр x үшін: p = lower_bound(t, x); p == len(t) болса t.append(x), әйтпесе t[p] = x; len(t) шығару"))
def _(r, big):
    n = r.randint(5000, 20000) if big else r.randint(3, 9)
    a = [r.randint(-10**9, 10**9) if big else r.randint(1, 9) for _ in range(n)]
    t = []
    for x in a:
        p = bisect_left(t, x)
        if p == len(t):
            t.append(x)
        else:
            t[p] = x
    return L(n, J(a)), L(len(t))


@problem("Ең ұзын ортақ ішкі тізбек", ["dp", "strings"], 1700, 3,
         "Екі жолдың ең ұзын ортақ ішкі тізбегінің (әріптерді өшіріп алуға болады) ұзындығын табыңыз.",
         "Екі жолда кіші латын әріптерінен тұратын $s$ және $t$ жолдары, ұзындықтары $1$-ден $1000$-ға дейін.",
         "Ұзындықты шығарыңыз.",
         ("Жолдардың префикстері бойынша жауапты есептеңіз.",
          "Алгоритм: екі өлшемді ДП.",
          "dp[i][j] = s[i-1] == t[j-1] болса dp[i-1][j-1] + 1, әйтпесе max(dp[i-1][j], dp[i][j-1])"))
def _(r, big):
    n, m = (r.randint(400, 800), r.randint(400, 800)) if big else (r.randint(2, 7), r.randint(2, 7))
    s = "".join(r.choice("abc") for _ in range(n))
    t = "".join(r.choice("abc") for _ in range(m))
    prev = [0] * (m + 1)
    for i in range(1, n + 1):
        cur = [0] * (m + 1)
        for j in range(1, m + 1):
            cur[j] = prev[j - 1] + 1 if s[i - 1] == t[j - 1] else max(prev[j], cur[j - 1])
        prev = cur
    return L(s, t), L(prev[m])


@problem("Монеталар жинағы", ["dp"], 1400, 3,
         "$n$ түрлі номиналды монета бар (әр түрден шексіз). $S$ соммасын ең аз монетамен төлеңіз. Мүмкін болмаса $-1$ шығарыңыз.",
         "Бірінші жолда $n, S$ ($1 \\le n \\le 100$, $1 \\le S \\le 10^4$). Екінші жолда $n$ номинал ($1 \\le c_i \\le 10^4$).",
         "Ең аз монета санын немесе $-1$ шығарыңыз.",
         ("Ашкөз әдіс әрдайым дұрыс жауап бермейді.",
          "Алгоритм: динамикалық бағдарламалау, $dp[s]$ — $s$ сомасына қажет ең аз монета.",
          "dp[0] = 0; s = 1..S үшін dp[s] = min(dp[s - c] + 1) барлық c <= s"))
def _(r, big):
    n = r.randint(10, 60) if big else r.randint(2, 4)
    S = r.randint(3000, 10000) if big else r.randint(5, 25)
    c = [r.randint(2, 500 if big else 9) for _ in range(n)]
    inf = 10**9
    dp = [0] + [inf] * S
    for s in range(1, S + 1):
        for x in c:
            if x <= s and dp[s - x] + 1 < dp[s]:
                dp[s] = dp[s - x] + 1
    return L(f"{n} {S}", J(c)), L(dp[S] if dp[S] < inf else -1)


@problem("Матрицадағы жол", ["dp"], 1300, 3,
         "$n \\times m$ кестенің әр ұяшығында бүтін сан бар. Сол жоғарғы ұяшықтан оң төменгі ұяшыққа тек оңға "
         "немесе төменге жүріп, өткен ұяшықтардағы сандардың қосындысын ең үлкен етіңіз.",
         "Бірінші жолда $n, m$ ($1 \\le n, m \\le 300$). Келесі $n$ жолда $m$ сан, модулі $10^4$-тен аспайды.",
         "Ең үлкен қосындыны шығарыңыз.",
         ("Ұяшыққа тек жоғарыдан немесе солдан келуге болады.",
          "Алгоритм: екі өлшемді ДП.",
          "dp[i][j] = a[i][j] + max(dp[i-1][j], dp[i][j-1]) (бар жағын ғана)"))
def _(r, big):
    n, m = (r.randint(100, 250), r.randint(100, 250)) if big else (r.randint(1, 4), r.randint(2, 4))
    g = [[r.randint(-10**4, 10**4) if big else r.randint(-5, 9) for _ in range(m)] for _ in range(n)]
    dp = [[0] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            best = None
            if i:
                best = dp[i - 1][j]
            if j and (best is None or dp[i][j - 1] > best):
                best = dp[i][j - 1]
            dp[i][j] = g[i][j] + (best or 0)
    return L(f"{n} {m}", *[J(row) for row in g]), L(dp[-1][-1])


@problem("Өңдеу арақашықтығы", ["dp", "strings"], 2000, 3,
         "Бір жолды екіншісіне айналдыру үшін бір әріпті қою, өшіру немесе ауыстыру амалдарын қолдануға болады. "
         "Қажет амалдардың ең аз санын табыңыз.",
         "Екі жолда кіші латын әріптерінен тұратын $s$ және $t$ жолдары, ұзындықтары $1$-ден $1000$-ға дейін.",
         "Амалдардың ең аз санын шығарыңыз.",
         ("Префикстер арасындағы арақашықтықты есептеңіз.",
          "Алгоритм: Левенштейн арақашықтығы (ДП).",
          "dp[i][0] = i; dp[0][j] = j; dp[i][j] = min(dp[i-1][j] + 1, dp[i][j-1] + 1, dp[i-1][j-1] + (s[i-1] != t[j-1]))"))
def _(r, big):
    n, m = (r.randint(300, 600), r.randint(300, 600)) if big else (r.randint(2, 7), r.randint(2, 7))
    s = "".join(r.choice("abc") for _ in range(n))
    t = "".join(r.choice("abc") for _ in range(m))
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (s[i - 1] != t[j - 1]))
        prev = cur
    return L(s, t), L(prev[m])


# ================================= 5. Графтар ================================


def _edges(r, n, m):
    out = []
    for _ in range(m):
        u = r.randint(1, n)
        v = r.randint(1, n)
        while v == u:
            v = r.randint(1, n)
        out.append((u, v))
    return out


def _adj(n, edges, directed=False):
    g = [[] for _ in range(n + 1)]
    for u, v in edges:
        g[u].append(v)
        if not directed:
            g[v].append(u)
    return g


@problem("Байланыс компоненттері", ["graphs"], 1100, 4,
         "Бағытсыз графта $n$ төбе және $m$ қабырға бар. Байланыс компоненттерінің санын табыңыз.",
         "Бірінші жолда $n, m$ ($2 \\le n \\le 10^5$, $0 \\le m \\le 2 \\cdot 10^5$). Келесі $m$ жолда $u, v$ — қабырға ұштары ($u \\ne v$, қайталануы мүмкін).",
         "Компоненттер санын шығарыңыз.",
         ("Әр байланыс аймағын бір рет аралаңыз.",
          "Алгоритм: тереңдікке немесе енге іздеу (DFS/BFS) не DSU.",
          "Әр төбе үшін: егер аралмаған болса ans++ және осы төбеден BFS жүргізіп, барлық жететіндерді белгілеу"))
def _(r, big):
    n = r.randint(1000, 3000) if big else r.randint(3, 9)
    m = r.randint(n // 2, n) if big else r.randint(0, 5)
    ed = _edges(r, n, m)
    g, seen, comp = _adj(n, ed), [False] * (n + 1), 0
    for s in range(1, n + 1):
        if not seen[s]:
            comp += 1
            seen[s] = True
            dq = deque([s])
            while dq:
                u = dq.popleft()
                for v in g[u]:
                    if not seen[v]:
                        seen[v] = True
                        dq.append(v)
    return L(f"{n} {m}", *[f"{u} {v}" for u, v in ed]), L(comp)


@problem("Ең қысқа жол", ["graphs"], 1300, 4,
         "Бағытсыз графта $1$-ші төбеден $n$-ші төбеге дейінгі ең аз қабырға санынан тұратын жолдың ұзындығын табыңыз.",
         "Бірінші жолда $n, m$ ($2 \\le n \\le 10^5$, $0 \\le m \\le 2 \\cdot 10^5$). Келесі $m$ жолда $u, v$ ($u \\ne v$).",
         "Қабырға санын шығарыңыз, жол жоқ болса $-1$.",
         ("Барлық қабырғаның салмағы бірдей — қашықтықты қабаттап есептеңіз.",
          "Алгоритм: ені бойынша іздеу (BFS).",
          "d[1] = 0; кезекке 1; кезек бос емес болғанда: u алу, көрші v аралмаған болса d[v] = d[u] + 1; d[n] шығару"))
def _(r, big):
    n = r.randint(1000, 3000) if big else r.randint(3, 8)
    m = r.randint(n, 2 * n) if big else r.randint(2, 8)
    ed = _edges(r, n, m)
    g = _adj(n, ed)
    d = [-1] * (n + 1)
    d[1] = 0
    dq = deque([1])
    while dq:
        u = dq.popleft()
        for v in g[u]:
            if d[v] < 0:
                d[v] = d[u] + 1
                dq.append(v)
    return L(f"{n} {m}", *[f"{u} {v}" for u, v in ed]), L(d[n])


@problem("Екі жақты граф", ["graphs"], 1500, 4,
         "Графтың төбелерін екі түске боялауға болса (әр қабырғаның ұштары әртүрлі түсті), ол екі жақты деп аталады. Графты тексеріңіз.",
         "Бірінші жолда $n, m$ ($1 \\le n \\le 10^5$, $0 \\le m \\le 2 \\cdot 10^5$). Келесі $m$ жолда $u, v$ ($u \\ne v$).",
         "Екі жақты болса `YES`, әйтпесе `NO` шығарыңыз.",
         ("Көршілер әрқашан қарама-қарсы түсте болуы керек.",
          "Алгоритм: BFS/DFS арқылы түске бояу.",
          "Әр компонентте бастапқы төбені 0 деп бояу; көршіні 1 - түс; бірдей түсті көрші кездессе NO"))
def _(r, big):
    n = r.randint(800, 2500) if big else r.randint(3, 8)
    m = r.randint(n // 2, n) if big else r.randint(2, 7)
    if r.random() < 0.5:
        side = [r.randint(0, 1) for _ in range(n + 1)]
        ed = []
        while len(ed) < m:
            u, v = r.randint(1, n), r.randint(1, n)
            if u != v and side[u] != side[v]:
                ed.append((u, v))
    else:
        ed = _edges(r, n, m)
    g, col, ok = _adj(n, ed), [-1] * (n + 1), True
    for s in range(1, n + 1):
        if col[s] >= 0:
            continue
        col[s] = 0
        dq = deque([s])
        while dq and ok:
            u = dq.popleft()
            for v in g[u]:
                if col[v] < 0:
                    col[v] = col[u] ^ 1
                    dq.append(v)
                elif col[v] == col[u]:
                    ok = False
    return L(f"{n} {m}", *[f"{u} {v}" for u, v in ed]), L("YES" if ok else "NO")


@problem("Лабиринт", ["graphs"], 1400, 4,
         "Лабиринт $n \\times m$ кесте, `.` — бос ұяшық, `#` — қабырға. Сол жоғарғы ұяшықтан оң төменгі ұяшыққа "
         "төрт бағытта (жоғары, төмен, солға, оңға) бос ұяшықтармен жүріп жетудің ең аз қадам санын табыңыз.",
         "Бірінші жолда $n, m$ ($1 \\le n, m \\le 500$). Келесі $n$ жолда $m$ таңбадан тұратын жол. Бастапқы және соңғы ұяшықтар әрқашан `.`.",
         "Қадам санын шығарыңыз, жету мүмкін болмаса $-1$.",
         ("Лабиринт — ұяшықтары төбе болатын граф.",
          "Алгоритм: BFS.",
          "Кезекке (0, 0); әр ұяшықтан 4 көршіге: шекара ішінде, '.' және аралмаған болса d + 1 орнату"))
def _(r, big):
    n, m = (r.randint(30, 80), r.randint(30, 80)) if big else (r.randint(2, 5), r.randint(2, 5))
    p = 0.28 if big else 0.3
    g = [["#" if r.random() < p else "." for _ in range(m)] for _ in range(n)]
    g[0][0] = g[n - 1][m - 1] = "."
    d = [[-1] * m for _ in range(n)]
    d[0][0] = 0
    dq = deque([(0, 0)])
    while dq:
        x, y = dq.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = x + dx, y + dy
            if 0 <= a < n and 0 <= b < m and g[a][b] == "." and d[a][b] < 0:
                d[a][b] = d[x][y] + 1
                dq.append((a, b))
    return L(f"{n} {m}", *["".join(row) for row in g]), L(d[n - 1][m - 1])


@problem("Салмақты ең қысқа жол", ["graphs"], 1800, 4,
         "Бағытсыз графтың әр қабырғасының теріс емес салмағы бар. $1$-ші төбеден $n$-ші төбеге дейінгі ең қысқа жолдың салмағын табыңыз.",
         "Бірінші жолда $n, m$ ($2 \\le n \\le 10^5$, $0 \\le m \\le 2 \\cdot 10^5$). Келесі $m$ жолда $u, v, w$ ($u \\ne v$, $0 \\le w \\le 10^9$).",
         "Ең қысқа жол ұзындығын шығарыңыз, жол жоқ болса $-1$.",
         ("Қабырға салмақтары әртүрлі болғандықтан, BFS жеткіліксіз.",
          "Алгоритм: Дейкстра алгоритмі (екілік үйме).",
          "d[1] = 0; үймеге (0, 1); ең кіші (dist, u) алу; ескірген болса өткізу; көрші v үшін d[u] + w < d[v] болса жаңарту"))
def _(r, big):
    n = r.randint(800, 2000) if big else r.randint(3, 7)
    m = r.randint(n, 3 * n) if big else r.randint(2, 8)
    ed = [(u, v, r.randint(0, 10**9 if big else 9)) for u, v in _edges(r, n, m)]
    g = [[] for _ in range(n + 1)]
    for u, v, w in ed:
        g[u].append((v, w))
        g[v].append((u, w))
    inf = float("inf")
    d = [inf] * (n + 1)
    d[1] = 0
    pq = [(0, 1)]
    while pq:
        du, u = heapq.heappop(pq)
        if du > d[u]:
            continue
        for v, w in g[u]:
            if du + w < d[v]:
                d[v] = du + w
                heapq.heappush(pq, (d[v], v))
    return L(f"{n} {m}", *[f"{u} {v} {w}" for u, v, w in ed]), L(d[n] if d[n] < inf else -1)


@problem("Циклды іздеу", ["graphs"], 1600, 4,
         "Бағытталған графта $n$ төбе және $m$ доға бар. Графта цикл бар ма?",
         "Бірінші жолда $n, m$ ($1 \\le n \\le 10^5$, $0 \\le m \\le 2 \\cdot 10^5$). Келесі $m$ жолда $u \\to v$ доғасы ($u \\ne v$).",
         "Цикл болса `YES`, әйтпесе `NO` шығарыңыз.",
         ("Циклсыз графта төбелерді доғалар бір бағытта болатындай тізуге болады.",
          "Алгоритм: топологиялық сұрыптау (Кан алгоритмі) немесе DFS-те түстер.",
          "Кірісі 0 төбелерді кезекке салу; шығарып, көршілердің кірісін кемітіп барамыз; өңделген төбелер саны < n болса цикл бар"))
def _(r, big):
    n = r.randint(800, 2500) if big else r.randint(3, 8)
    m = r.randint(n // 2, 2 * n) if big else r.randint(2, 7)
    order = list(range(1, n + 1))
    r.shuffle(order)
    pos = {v: i for i, v in enumerate(order)}
    ed = []
    while len(ed) < m:
        u, v = r.randint(1, n), r.randint(1, n)
        if u != v and pos[u] < pos[v]:
            ed.append((u, v))
    if r.random() < 0.5:
        u, v = r.randint(1, n), r.randint(1, n)
        while u == v:
            v = r.randint(1, n)
        ed.append((u, v))
        ed = ed[-1:] + ed[:-1] if r.random() < 0.5 else ed
        m += 1
    g, indeg = _adj(n, ed, directed=True), [0] * (n + 1)
    for _u, v in ed:
        indeg[v] += 1
    dq = deque(v for v in range(1, n + 1) if indeg[v] == 0)
    done = 0
    while dq:
        u = dq.popleft()
        done += 1
        for v in g[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                dq.append(v)
    return L(f"{n} {m}", *[f"{u} {v}" for u, v in ed]), L("YES" if done < n else "NO")


# ===================== 6. Математика және сандар теориясы =====================


@problem("Екі санның ЕКОЕ", ["math"], 900, 5,
         "Екі натурал сан $a$ және $b$ берілген. Олардың ең кіші ортақ еселігін (ЕКОЕ) табыңыз.",
         "Бір жолда $a, b$ ($1 \\le a, b \\le 10^9$).",
         "ЕКОЕ мәнін шығарыңыз (ол $10^{18}$-нан аспайды).",
         ("ЕКОЕ мен ЕҮОБ арасында байланыс бар.",
          "Формула: $\\operatorname{lcm}(a,b)=a \\cdot b / \\gcd(a,b)$; ЕҮОБ-ты Евклид алгоритмімен табыңыз.",
          "g = gcd(a, b); жауап = a // g * b (алдымен бөліңіз, сонда аралық сан тым үлкен болмайды)"))
def _(r, big):
    hi = 10**9 if big else 30
    a, b = r.randint(1, hi), r.randint(1, hi)
    return L(f"{a} {b}"), L(a * b // math.gcd(a, b))


@problem("Цифрлар қосындысы", ["math"], 800, 5,
         "Натурал $n$ саны берілген. Оның ондық жазбасындағы цифрлардың қосындысын табыңыз.",
         "Бір жолда $n$ ($1 \\le n \\le 10^{18}$).",
         "Цифрлар қосындысын шығарыңыз.",
         ("Санның соңғы цифрын $n \\bmod 10$ арқылы алуға болады.",
          "Алгоритм: цифрларды біртіндеп бөліп алу (немесе санды жол ретінде оқу).",
          "s = 0; n > 0 болғанда: s += n % 10; n //= 10; s шығару"))
def _(r, big):
    n = r.randint(10**17, 10**18) if big else r.randint(1, 5000)
    return L(n), L(sum(map(int, str(n))))


@problem("Модуль бойынша дәреже", ["math"], 1400, 5,
         "$a^b \\bmod m$ мәнін табыңыз.",
         "Бір жолда $a, b, m$ ($1 \\le a, b \\le 10^{18}$, $2 \\le m \\le 10^9$).",
         "$a^b$ санының $m$ бойынша қалдығын шығарыңыз.",
         ("$b$ өте үлкен, $a$ санын $b$ рет көбейту мүмкін емес.",
          "Алгоритм: екілік дәрежелеу ($b$ санының биттері бойынша квадраттау).",
          "res = 1; a %= m; b > 0 болғанда: егер b тақ болса res = res*a % m; a = a*a % m; b //= 2"))
def _(r, big):
    if big:
        a, b, m = r.randint(1, 10**18), r.randint(1, 10**18), r.randint(2, 10**9)
    else:
        a, b, m = r.randint(1, 50), r.randint(1, 50), r.randint(2, 100)
    return L(f"{a} {b} {m}"), L(pow(a, b, m))


def _factorize(n):
    f, d = {}, 2
    while d * d <= n:
        while n % d == 0:
            f[d] = f.get(d, 0) + 1
            n //= d
        d += 1 if d == 2 else 2
    if n > 1:
        f[n] = f.get(n, 0) + 1
    return f


@problem("Әртүрлі жай бөлгіштер", ["math"], 1300, 5,
         "$n$ санының әртүрлі жай бөлгіштерінің санын табыңыз.",
         "Бір жолда $n$ ($2 \\le n \\le 10^{12}$).",
         "Әртүрлі жай бөлгіштер санын шығарыңыз.",
         ("Санды жай көбейткіштерге жіктеу керек.",
          "Алгоритм: $d$ бойынша $\\sqrt{n}$-ге дейін бөлу; қалған $1$-ден үлкен сан да жай бөлгіш.",
          "d = 2; d*d <= n болғанда: егер n % d == 0: cnt++ және n-ді d-ға толық бөлу; d++; соңында n > 1 болса cnt++"))
def _(r, big):
    if big:
        n = r.choice([999999999989, 6469693230 * r.randint(1, 100), r.randint(10**11, 10**12), 2**39])
    else:
        n = r.randint(2, 200)
    return L(n), L(len(_factorize(n)))


@problem("Эйлер функциясы", ["math"], 1500, 5,
         "$\\varphi(n)$ санын табыңыз — $1$-ден $n$-ге дейінгі $n$ санымен өзара жай сандардың саны.",
         "Бір жолда $n$ ($1 \\le n \\le 10^{12}$).",
         "$\\varphi(n)$ мәнін шығарыңыз.",
         ("$n$ санының жай бөлгіштері керек.",
          "Формула: $\\varphi(n)=n \\prod (1 - 1/p)$, $p$ — $n$ санының әртүрлі жай бөлгіштері.",
          "res = n; әр жай бөлгіш p үшін: res -= res // p"))
def _(r, big):
    n = r.choice([999999999989, r.randint(10**11, 10**12), 2**38 * 3, r.randint(10**9, 10**12)]) if big else r.randint(1, 200)
    res = n
    for p in _factorize(n):
        res -= res // p
    return L(n), L(res)


@problem("Биномдық коэффициент", ["math"], 1600, 5,
         "$C(n, k)$ санын табыңыз — $n$ элементтен $k$ элемент таңдау тәсілдерінің саны. "
         "Жауапты $10^9+7$ модулімен шығарыңыз.",
         "Бір жолда $n, k$ ($0 \\le k \\le n \\le 10^6$).",
         "$C(n,k) \\bmod (10^9+7)$ мәнін шығарыңыз.",
         ("Формула: $C(n,k)=\\dfrac{n!}{k!(n-k)!}$, бірақ модуль бойынша бөлуді тікелей жасауға болмайды.",
          "Алгоритм: факториалдарды есептеп, бөлудің орнына кері элементті (Ферма теоремасы) қолдану.",
          "fact[i] = fact[i-1]*i % P; жауап = fact[n] * pow(fact[k], P-2, P) % P * pow(fact[n-k], P-2, P) % P"))
def _(r, big):
    n = r.randint(10**5, 2 * 10**5) if big else r.randint(0, 12)
    k = r.randint(0, n)
    return L(f"{n} {k}"), L(math.comb(n, k) % MOD)


# ============================ 7. Ашкөз алгоритмдер ============================


@problem("Ең үлкен сан", ["greedy", "sorting"], 1400, 6,
         "$n$ теріс емес бүтін сан берілген. Оларды қандай да бір ретпен қатар (жол ретінде) жазып, ең үлкен сан алу керек.",
         "Бірінші жолда $n$ ($1 \\le n \\le 10^5$). Екінші жолда $n$ сан, әрқайсысы $0$-ден $10^9$-ға дейін (бастапқы нөлсіз жазылған).",
         "Ең үлкен санды шығарыңыз (барлық сан $0$ болса, тек $0$).",
         ("Екі $a$ және $b$ саны үшін $ab$ мен $ba$ жазбасының қайсысы үлкен?",
          "Алгоритм: сандарды жол ретінде $a+b > b+a$ шарты бойынша сұрыптау.",
          "Сандарды жолға айналдыру; (a, b) үшін a+b > b+a болса a алдында тұратындай сұрыптау; біріктіру; нәтиже '0'-ден басталса '0' шығару"))
def _(r, big):
    n = r.randint(500, 3000) if big else r.randint(2, 6)
    a = [r.choice([r.randint(0, 10**9), r.randint(0, 1000), r.randint(0, 99)]) if big else r.randint(0, 100) for _ in range(n)]
    s = "".join(sorted(map(str, a), key=cmp_to_key(lambda x, y: -1 if x + y > y + x else (1 if x + y < y + x else 0))))
    return L(n, J(a)), L("0" if s[0] == "0" else s)


@problem("Тапсырмалар мерзімі", ["greedy", "sorting"], 1600, 6,
         "$n$ тапсырма бар. Әр тапсырманы орындауға тура $1$ күн кетеді, күндер $1$-ден басталады. "
         "$i$-ші тапсырманы $d_i$-ші күннен кешіктірмей орындау керек, ол $p_i$ пайда әкеледі. "
         "Бір күнде тек бір тапсырма орындалады. Ең көп пайданы табыңыз.",
         "Бірінші жолда $n$ ($1 \\le n \\le 10^5$). Келесі $n$ жолда $d_i, p_i$ ($1 \\le d_i \\le 10^9$, $1 \\le p_i \\le 10^9$).",
         "Ең көп жиынтық пайданы шығарыңыз.",
         ("Мерзімі кеш тапсырмаларды кейінгі күндерге қалдыруға болады.",
          "Алгоритм: мерзім бойынша сұрыптап, пайдалардың минимум-үйіндісін ұстау.",
          "d бойынша сұрыптау; әр (d, p) үшін p-ны үйіндіге салу; үйінді өлшемі d-дан асса ең кіші пайданы алып тастау; үйіндідегілердің қосындысы"))
def _(r, big):
    n = r.randint(500, 3000) if big else r.randint(2, 7)
    dmax = n if big else 5
    t = [(r.randint(1, dmax), r.randint(1, 10**9 if big else 20)) for _ in range(n)]
    h = []
    for d, p in sorted(t):
        heapq.heappush(h, p)
        if len(h) > d:
            heapq.heappop(h)
    return L(n, *[f"{d} {p}" for d, p in t]), L(sum(h))


@problem("Қосу құны", ["greedy"], 1500, 6,
         "$n$ сан берілген. Әр қадамда екі санды алып, оларды қосындысымен ауыстырады; бұл қадамның құны — сол қосынды. "
         "Бір ғана сан қалғанша қосу керек. Жиынтық құнның ең азын табыңыз.",
         "Бірінші жолда $n$ ($2 \\le n \\le 10^5$). Екінші жолда $n$ сан, әрқайсысы $1$-ден $10^9$-ға дейін.",
         "Ең аз жиынтық құнды шығарыңыз.",
         ("Қай екі санды қосқан тиімді: үлкендерін бе, кішілерін бе?",
          "Алгоритм: әр қадамда ең кіші екі санды алу (минимум-үйінді).",
          "Үйіндіге барлық санды салу; үйіндіде 1-ден көп элемент болғанда: x, y = ең кіші екеуі; ans += x + y; x + y қайта салу"))
def _(r, big):
    n = r.randint(500, 3000) if big else r.randint(2, 7)
    a = [r.randint(1, 10**9 if big else 20) for _ in range(n)]
    h = a[:]
    heapq.heapify(h)
    ans = 0
    while len(h) > 1:
        x, y = heapq.heappop(h), heapq.heappop(h)
        ans += x + y
        heapq.heappush(h, x + y)
    return L(n, J(a)), L(ans)


@problem("Қайықтар", ["greedy", "sorting"], 1200, 6,
         "$n$ адам өзеннен өтуі керек. Қайыққа ең көбі екі адам сияды, олардың салмақтарының қосындысы $W$-дан аспауы тиіс. "
         "Әр адамның салмағы $W$-дан аспайды. Қажет қайықтардың ең аз санын табыңыз.",
         "Бірінші жолда $n, W$ ($1 \\le n \\le 10^5$, $1 \\le W \\le 10^9$). Екінші жолда $n$ салмақ, әрқайсысы $1$-ден $W$-ға дейін.",
         "Қайықтардың ең аз санын шығарыңыз.",
         ("Ең ауыр адамды кіммен жұптау тиімді?",
          "Алгоритм: сұрыптап, екі көрсеткіш (ең жеңіл және ең ауыр).",
          "Сұрыптау; i = 0, j = n-1; i <= j болғанда: егер a[i] + a[j] <= W болса i++; j--; ans++"))
def _(r, big):
    n = r.randint(500, 3000) if big else r.randint(2, 8)
    w = r.randint(10**8, 10**9) if big else r.randint(10, 30)
    a = [r.randint(1, w) for _ in range(n)]
    b = sorted(a)
    i, j, ans = 0, n - 1, 0
    while i <= j:
        if b[i] + b[j] <= w:
            i += 1
        j -= 1
        ans += 1
    return L(f"{n} {w}", J(a)), L(ans)


@problem("Ең аз күту уақыты", ["greedy", "sorting"], 1000, 6,
         "Кезекте $n$ клиент тұр, $i$-ші клиентке қызмет көрсету $t_i$ минут алады. Клиенттер бір-бірден қызмет алады. "
         "Клиенттің күту уақыты — оның алдындағылардың қызметінің жалпы ұзақтығы. Клиенттерді қалауымызша орналастырып, "
         "барлық клиенттің күту уақытының қосындысын ең аз етіңіз.",
         "Бірінші жолда $n$ ($1 \\le n \\le 10^5$). Екінші жолда $n$ сан $t_i$ ($1 \\le t_i \\le 10^4$).",
         "Күту уақытының ең аз қосындысын шығарыңыз.",
         ("Ұзақ қызметті бірінші қойсақ, одан кейінгілердің бәрі күтеді.",
          "Алгоритм: $t_i$ өсу ретімен сұрыптау.",
          "Сұрыптау; pref = 0; әр t үшін: ans += pref; pref += t"))
def _(r, big):
    n = r.randint(1000, 5000) if big else r.randint(1, 7)
    t = [r.randint(1, 10**4 if big else 15) for _ in range(n)]
    pref = ans = 0
    for x in sorted(t):
        ans += pref
        pref += x
    return L(n, J(t)), L(ans)


# ============ 8. Сұрыптау, екілік іздеу, жолдар, DP, графтар (қосымша) ============


@problem("Бүтін квадрат түбір", ["binary-search", "math"], 1100, 1,
         "Натурал $n$ саны берілген. $x^2 \\le n$ шартын қанағаттандыратын ең үлкен бүтін $x$ санын табыңыз.",
         "Бір жолда $n$ ($1 \\le n \\le 10^{18}$).",
         "Ең үлкен $x$ санын шығарыңыз.",
         ("$x$ өскен сайын $x^2$ де өседі.",
          "Алгоритм: жауап бойынша екілік іздеу.",
          "lo = 0, hi = 10^9; lo < hi болғанда: mid = (lo + hi + 1) / 2; егер mid*mid <= n болса lo = mid, әйтпесе hi = mid - 1"))
def _(r, big):
    n = r.choice([10**18, r.randint(1, 10**18), (10**9 - 1) ** 2, r.randint(1, 10**9) ** 2]) if big else r.randint(1, 100)
    return L(n), L(math.isqrt(n))


@problem("Ең жақын элемент", ["binary-search", "sorting"], 1200, 1,
         "Өсу ретімен сұрыпталған $n$ бүтін сан және $q$ сұрау берілген. Әр сұрауда $x$ саны беріледі: "
         "массивтегі $x$-ке ең жақын элементті табыңыз (екі элемент бірдей жақын болса, кішісін).",
         "Бірінші жолда $n, q$ ($1 \\le n, q \\le 10^5$). Екінші жолда $n$ сан (өсу ретімен, кемімей), модулі $10^9$-дан аспайды. Келесі $q$ жолда бір-бір $x$ ($|x| \\le 10^9$).",
         "Әр сұрау үшін бір жолда жауап шығарыңыз.",
         ("Массив сұрыпталған: $x$-ке жақын элементтер оның орнының екі жағында болады.",
          "Алгоритм: екілік іздеумен $x$-тен кіші емес бірінші элементті табып, оның және алдындағының қайсысы жақын екенін салыстыру.",
          "i = lower_bound(x); кандидаттар: a[i-1] (егер бар болса), a[i] (егер бар болса); (|a - x|, a) бойынша ең кішісін таңдау"))
def _(r, big):
    n = r.randint(500, 2000) if big else r.randint(1, 6)
    q = r.randint(500, 2000) if big else r.randint(1, 6)
    hi = 10**9 if big else 20
    a = sorted(r.randint(-hi, hi) for _ in range(n))
    qs = [r.randint(-hi - 5, hi + 5) for _ in range(q)]
    out = []
    for x in qs:
        i = bisect_left(a, x)
        c = ([a[i - 1]] if i > 0 else []) + ([a[i]] if i < n else [])
        out.append(min(c, key=lambda v: (abs(v - x), v)))
    return L(f"{n} {q}", J(a), *qs), L(*out)


@problem("Массивті бөлу", ["binary-search", "greedy"], 1700, 1,
         "$n$ натурал саннан тұратын массивті $k$ бос емес іргелес бөлікке бөлу керек. Бөліктің қосындысы — ондағы сандардың қосындысы. "
         "Бөліктердің ең үлкен қосындысын мүмкіндігінше кіші етіңіз.",
         "Бірінші жолда $n, k$ ($1 \\le k \\le n \\le 10^5$). Екінші жолда $n$ сан, әрқайсысы $1$-ден $10^9$-ға дейін.",
         "Ең үлкен бөлік қосындысының ең аз мүмкін мәнін шығарыңыз.",
         ("Ең үлкен қосынды $C$ болсын деп алсақ, бөліктерді ашкөздікпен құруға болады.",
          "Алгоритм: $C$ бойынша екілік іздеу және ашкөз тексеру (бөліктер саны $k$-дан аспай ма).",
          "lo = max(a), hi = sum(a); lo < hi болғанда: mid; егер ok(mid) болса hi = mid, әйтпесе lo = mid + 1; ok: ағымдағы қосынды mid-тен асса жаңа бөлік бастау"))
def _(r, big):
    n = r.randint(500, 3000) if big else r.randint(2, 8)
    k = r.randint(1, n)
    a = [r.randint(1, 10**9 if big else 20) for _ in range(n)]

    def ok(cap):
        parts, cur = 1, 0
        for x in a:
            if cur + x > cap:
                parts += 1
                cur = x
            else:
                cur += x
        return parts <= k

    lo, hi = max(a), sum(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if ok(mid):
            hi = mid
        else:
            lo = mid + 1
    return L(f"{n} {k}", J(a)), L(lo)


@problem("Кесінділерді біріктіру", ["sorting"], 1300, 1,
         "Санау түзуінде $n$ кесінді берілген: $i$-ші кесінді $[l_i, r_i]$. Ортақ нүктесі бар кесінділер біріктіріледі. "
         "Барлық кесінділердің бірігуінің жалпы ұзындығын табыңыз.",
         "Бірінші жолда $n$ ($1 \\le n \\le 10^5$). Келесі $n$ жолда $l_i, r_i$ ($-10^9 \\le l_i \\le r_i \\le 10^9$).",
         "Бірігудің жалпы ұзындығын шығарыңыз.",
         ("Кесінділерді сол жақ ұшы бойынша сұрыптаған жөн.",
          "Алгоритм: сұрыптау және ағымдағы біріктірілген кесіндіні кеңейту.",
          "l бойынша сұрыптау; (cl, cr) = бірінші; келесі (l, r): егер l <= cr болса cr = max(cr, r), әйтпесе ans += cr - cl және (cl, cr) = (l, r); соңында ans += cr - cl"))
def _(r, big):
    n = r.randint(500, 3000) if big else r.randint(1, 6)
    hi = 10**6 if big else 15
    iv = []
    for _ in range(n):
        l = r.randint(-hi, hi)
        iv.append((l, min(hi, l + r.randint(0, hi // 100 if big else 4))))
    s = sorted(iv)
    ans, (cl, cr) = 0, s[0]
    for l, rr in s[1:]:
        if l <= cr:
            cr = max(cr, rr)
        else:
            ans += cr - cl
            cl, cr = l, rr
    ans += cr - cl
    return L(n, *[f"{l} {rr}" for l, rr in iv]), L(ans)


@problem("Ең жиі кездесетін сан", ["sorting"], 900, 1,
         "$n$ бүтін сан берілген. Ең көп рет кездесетін санды табыңыз. Бірнеше сан бірдей жиі кездессе, олардың кішісін шығарыңыз.",
         "Бірінші жолда $n$ ($1 \\le n \\le 10^5$). Екінші жолда $n$ бүтін сан, модулі $10^9$-дан аспайды.",
         "Ең жиі кездесетін санды шығарыңыз.",
         ("Бірдей сандар сұрыпталған массивте қатар тұрады.",
          "Алгоритм: сұрыптап, қатар тұрған тең сандар топтарының ұзындығын санау (немесе сөздік).",
          "Сұрыптау; топтар бойынша ұзындықты есептеу; ең ұзын топтардың ішінен ең кіші санды таңдау"))
def _(r, big):
    n = r.randint(1000, 5000) if big else r.randint(1, 9)
    pool = [r.randint(-10**9, 10**9) for _ in range(30)] if big else list(range(-3, 4))
    a = [r.choice(pool) for _ in range(n)]
    c = Counter(a)
    m = max(c.values())
    return L(n, J(a)), L(min(v for v, k in c.items() if k == m))


@problem("Дауысты әріптер", ["strings"], 800, 2,
         "Кіші латын әріптерінен тұратын жол берілген. Ондағы дауысты әріптердің ($a, e, i, o, u$) санын табыңыз.",
         "Бір жолда $s$ жолы ($1 \\le |s| \\le 10^5$), тек кіші латын әріптері.",
         "Дауыстылар санын шығарыңыз.",
         ("Әр әріпті дауыстылар жиынымен салыстырыңыз.",
          "Алгоритм: жолды бір рет аралау.",
          "cnt = 0; әр c үшін: егер c 'aeiou' ішінде болса cnt++"))
def _(r, big):
    n = r.randint(1000, 5000) if big else r.randint(1, 12)
    s = "".join(r.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(n))
    return L(s), L(sum(ch in "aeiou" for ch in s))


@problem("Циклдік жылжу", ["strings"], 1100, 2,
         "Екі жол $s$ және $t$ берілген. $t$ жолын $s$ жолын циклдік жылжыту арқылы алуға бола ма? "
         "(Циклдік жылжу: алғашқы бірнеше таңбаны жолдың соңына көшіру.)",
         "Бірінші жолда $s$, екінші жолда $t$ ($1 \\le |s|, |t| \\le 10^5$), кіші латын әріптері.",
         "Алуға болса `YES`, болмаса `NO` шығарыңыз.",
         ("$s$ жолының барлық жылжуы $s+s$ жолының ішкі жолдары болады.",
          "Алгоритм: ұзындықтары тең болса, $t$ жолы $s+s$ ішінде кездесе ме деп тексеру.",
          "Егер len(s) != len(t) болса NO; әйтпесе t in s + s болса YES, әйтпесе NO"))
def _(r, big):
    n = r.randint(1000, 5000) if big else r.randint(1, 8)
    s = "".join(r.choice("ab" if not big else "abc") for _ in range(n))
    k = r.randint(0, n - 1)
    t = s[k:] + s[:k]
    mode = r.random()
    if mode < 0.4:
        i = r.randrange(n)
        t = t[:i] + ("a" if t[i] != "a" else "b") + t[i + 1:]
    elif mode < 0.5:
        t = t + "a"
    return L(s, t), L("YES" if len(s) == len(t) and t in s + s else "NO")


@problem("Префикс-функция", ["strings"], 1700, 2,
         "$s$ жолы берілген. Әр $i$ үшін $s[1..i]$ жолының өзінен басқа ең ұзын префиксін табыңыз, "
         "ол сол жолдың суффиксі де болсын. Яғни префикс-функцияны есептеңіз.",
         "Бір жолда $s$ жолы ($1 \\le |s| \\le 10^5$), кіші латын әріптері.",
         "$|s|$ сан шығарыңыз: әр префикс үшін сол ұзындық.",
         ("Алдыңғы префикстің жауабын келесісін табу үшін пайдалануға болады.",
          "Алгоритм: Кнут — Моррис — Пратт (КМП) префикс-функциясы.",
          "pi[0] = 0; әр i үшін: k = pi[i-1]; k > 0 және s[i] != s[k] болғанда k = pi[k-1]; егер s[i] == s[k] болса k++; pi[i] = k"))
def _(r, big):
    n = r.randint(1000, 5000) if big else r.randint(1, 12)
    s = "".join(r.choice("ab") for _ in range(n))
    pi = [0] * n
    for i in range(1, n):
        k = pi[i - 1]
        while k and s[i] != s[k]:
            k = pi[k - 1]
        if s[i] == s[k]:
            k += 1
        pi[i] = k
    return L(s), L(J(pi))


@problem("Қайталанбайтын ең ұзын ішкі жол", ["strings"], 1400, 2,
         "Жол берілген. Ешбір таңбасы қайталанбайтын ең ұзын ішкі жолдың (қатар тұрған таңбалар) ұзындығын табыңыз.",
         "Бір жолда $s$ жолы ($1 \\le |s| \\le 10^5$), кіші латын әріптері.",
         "Ең ұзын ішкі жолдың ұзындығын шығарыңыз.",
         ("Ішкі жолдың сол ұшын жылжытып, оң ұшын біртіндеп кеңейтіңіз.",
          "Алгоритм: екі көрсеткіш (жылжымалы терезе) және әр таңбаның соңғы орны.",
          "left = 0; әр right үшін: егер s[right] терезеде болса left = max(left, last[s[right]] + 1); last[s[right]] = right; ans = max(ans, right - left + 1)"))
def _(r, big):
    n = r.randint(1000, 5000) if big else r.randint(1, 12)
    s = "".join(r.choice("abcdefghij" if big else "abc") for _ in range(n))
    last, left, ans = {}, 0, 0
    for i, ch in enumerate(s):
        if ch in last and last[ch] >= left:
            left = last[ch] + 1
        last[ch] = i
        ans = max(ans, i - left + 1)
    return L(s), L(ans)


@problem("Қосынды құру", ["recursion"], 1300, 2,
         "$n$ натурал сан берілген. Қосындысы дәл $S$ болатын ішкі жиындардың (элементтердің позициялары бойынша) санын табыңыз.",
         "Бірінші жолда $n, S$ ($1 \\le n \\le 16$, $1 \\le S \\le 1600$). Екінші жолда $n$ сан, әрқайсысы $1$-ден $100$-ге дейін.",
         "Ішкі жиындар санын шығарыңыз.",
         ("Әр элементті не аламыз, не алмаймыз.",
          "Алгоритм: рекурсия (қайтарымды іздеу) немесе биттік маскалар; $2^{16}$ комбинация аз.",
          "go(i, sum): i == n болса sum == S ? 1 : 0; әйтпесе go(i+1, sum) + go(i+1, sum + a[i])"))
def _(r, big):
    n = r.randint(12, 16) if big else r.randint(1, 6)
    a = [r.randint(1, 100 if big else 9) for _ in range(n)]
    s = r.randint(max(1, sum(a) // 4), max(1, sum(a) // 2))
    cnt = {0: 1}
    for x in a:
        new = dict(cnt)
        for v, c in cnt.items():
            new[v + x] = new.get(v + x, 0) + c
        cnt = new
    return L(f"{n} {s}", J(a)), L(cnt.get(s, 0))


def _fib(n):
    if n == 0:
        return 0, 1
    a, b = _fib(n >> 1)
    c = a * ((2 * b - a) % MOD) % MOD
    d = (a * a + b * b) % MOD
    return (d, (c + d) % MOD) if n & 1 else (c, d)


@problem("Үлкен Фибоначчи", ["math", "recursion"], 1900, 2,
         "Фибоначчи сандары: $F_0=0$, $F_1=1$, $F_n=F_{n-1}+F_{n-2}$. $F_n \\bmod (10^9+7)$ мәнін табыңыз.",
         "Бір жолда $n$ ($0 \\le n \\le 10^{18}$).",
         "$F_n$ санын $10^9+7$ модулімен шығарыңыз.",
         ("$n$ өте үлкен, барлық сандарды есептеу мүмкін емес.",
          "Алгоритм: екі еселеу формулалары ($F_{2k}$ және $F_{2k+1}$ арқылы) немесе матрицаны дәрежелеу.",
          "F(2k) = F(k) * (2*F(k+1) - F(k)); F(2k+1) = F(k)^2 + F(k+1)^2; рекурсия тереңдігі $\\log n$"))
def _(r, big):
    n = r.choice([10**18, r.randint(1, 10**18), r.randint(10**9, 10**12)]) if big else r.randint(0, 30)
    return L(n), L(_fib(n)[0])


@problem("Көрші емес сандар", ["dp"], 1200, 3,
         "$n$ теріс емес бүтін сан берілген. Қатар тұрған екі санды бірге алуға болмайды. Алынған сандардың қосындысын ең үлкен етіңіз.",
         "Бірінші жолда $n$ ($1 \\le n \\le 10^5$). Екінші жолда $n$ сан, әрқайсысы $0$-ден $10^4$-ке дейін.",
         "Ең үлкен қосындыны шығарыңыз.",
         ("$i$-ші санды алсақ, $(i-1)$-ші санды алмаймыз.",
          "Алгоритм: динамикалық бағдарламалау: $dp_i = \\max(dp_{i-1},\\, dp_{i-2} + a_i)$.",
          "prev2 = 0, prev1 = 0; әр x үшін: cur = max(prev1, prev2 + x); prev2 = prev1; prev1 = cur; prev1 шығару"))
def _(r, big):
    n = r.randint(1000, 5000) if big else r.randint(1, 8)
    a = [r.randint(0, 10**4 if big else 20) for _ in range(n)]
    p2 = p1 = 0
    for x in a:
        p2, p1 = p1, max(p1, p2 + x)
    return L(n, J(a)), L(p1)


@problem("Ең үлкен ішкі массив қосындысы", ["dp"], 1200, 3,
         "$n$ бүтін санның тізбегі берілген. Қатар тұрған бос емес бөліктің ең үлкен қосындысын табыңыз.",
         "Бірінші жолда $n$ ($1 \\le n \\le 10^5$). Екінші жолда $n$ сан, модулі $10^4$-тен аспайды.",
         "Ең үлкен қосындыны шығарыңыз.",
         ("Әр орында аяқталатын ең жақсы бөлікті ойлаңыз.",
          "Алгоритм: Кадане алгоритмі.",
          "cur = a[0]; best = a[0]; әр x үшін: cur = max(x, cur + x); best = max(best, cur)"))
def _(r, big):
    n = r.randint(1000, 5000) if big else r.randint(1, 9)
    a = [r.randint(-10**4, 10**4) if big else r.randint(-9, 9) for _ in range(n)]
    cur = best = a[0]
    for x in a[1:]:
        cur = max(x, cur + x)
        best = max(best, cur)
    return L(n, J(a)), L(best)


@problem("Кедергілі торда жолдар", ["dp"], 1400, 3,
         "$n \\times m$ өлшемді тор берілген: `.` — бос, `#` — кедергі. Жоғарғы сол ұяшықтан төменгі оң ұяшыққа "
         "тек оңға немесе төменге жүріп, кедергісіз неше жолмен жетуге болады? Жауапты $10^9+7$ модулімен шығарыңыз.",
         "Бірінші жолда $n, m$ ($1 \\le n, m \\le 1000$). Келесі $n$ жолда $m$ таңбадан тұратын жол.",
         "Жолдар санын $10^9+7$ модулімен шығарыңыз (басталатын немесе аяқталатын ұяшық кедергі болса, $0$).",
         ("Ұяшыққа тек жоғарыдан немесе солдан келуге болады.",
          "Алгоритм: торлы динамикалық бағдарламалау: $dp[i][j]=dp[i-1][j]+dp[i][j-1]$, кедергіде $0$.",
          "dp[0][0] = 1 (егер бос болса); кедергі үшін dp = 0; әйтпесе dp[i][j] = (dp[i-1][j] + dp[i][j-1]) % P"))
def _(r, big):
    n, m = (r.randint(60, 120), r.randint(60, 120)) if big else (r.randint(1, 5), r.randint(1, 5))
    p = 0.08 if big else 0.2
    g = [["#" if r.random() < p else "." for _ in range(m)] for _ in range(n)]
    if r.random() < 0.8:
        g[0][0] = g[n - 1][m - 1] = "."
    dp = [[0] * m for _ in range(n)]
    for i in range(n):
        for j in range(m):
            if g[i][j] == "#":
                continue
            if i == 0 and j == 0:
                dp[i][j] = 1
            else:
                dp[i][j] = ((dp[i - 1][j] if i else 0) + (dp[i][j - 1] if j else 0)) % MOD
    return L(f"{n} {m}", *["".join(row) for row in g]), L(dp[n - 1][m - 1])


@problem("Санды қосылғыштарға жіктеу", ["dp", "math"], 1600, 3,
         "$n$ санын натурал сандардың қосындысы ретінде жазу тәсілдерінің санын табыңыз. Қосылғыштардың реті маңызды емес "
         "($3 = 1+2 = 2+1$ — бір тәсіл). Жауапты $10^9+7$ модулімен шығарыңыз.",
         "Бір жолда $n$ ($1 \\le n \\le 2000$).",
         "Тәсілдер санын $10^9+7$ модулімен шығарыңыз.",
         ("Қосылғыштарды өспейтін ретпен жазсақ, бірдей жіктеулер қайталанбайды.",
          "Алгоритм: монеталар есебіне ұқсас DP: $c = 1, 2, \\dots, n$ үшін $dp[s] \\mathrel{+}= dp[s-c]$.",
          "dp[0] = 1; c = 1..n үшін: s = c..n үшін: dp[s] = (dp[s] + dp[s-c]) % P; dp[n] шығару"))
def _(r, big):
    n = r.randint(500, 1000) if big else r.randint(1, 25)
    dp = [1] + [0] * n
    for c in range(1, n + 1):
        for s in range(c, n + 1):
            dp[s] = (dp[s] + dp[s - c]) % MOD
    return L(n), L(dp[n])


def _tree_edges(r, n):
    perm = list(range(1, n + 1))
    r.shuffle(perm)
    return [(perm[i], perm[r.randint(0, i - 1)]) for i in range(1, n)]


@problem("Төбелер дәрежесі", ["graphs"], 800, 4,
         "Бағытсыз графта $n$ төбе және $m$ қабырға бар. Төбенің дәрежесі — оған тиісті қабырғалар саны. "
         "Ең үлкен дәрежені табыңыз. Қабырғалар қайталануы мүмкін, әрқайсысы бөлек есептеледі.",
         "Бірінші жолда $n, m$ ($2 \\le n \\le 10^5$, $0 \\le m \\le 2 \\cdot 10^5$). Келесі $m$ жолда $u, v$ ($u \\ne v$).",
         "Ең үлкен дәрежені шығарыңыз.",
         ("Әр қабырға өзінің екі ұшының дәрежесін $1$-ге арттырады.",
          "Алгоритм: дәреже массивін есептеу.",
          "deg[u]++, deg[v]++ әр қабырға үшін; max(deg) шығару"))
def _(r, big):
    n = r.randint(500, 2000) if big else r.randint(2, 8)
    m = r.randint(n, 3 * n) if big else r.randint(0, 8)
    ed = _edges(r, n, m)
    deg = [0] * (n + 1)
    for u, v in ed:
        deg[u] += 1
        deg[v] += 1
    return L(f"{n} {m}", *[f"{u} {v}" for u, v in ed]), L(max(deg))


@problem("Қол жетімді төбелер", ["graphs"], 1200, 4,
         "Бағытталған графта $n$ төбе және $m$ доға бар. $1$-ші төбеден жүріп жететін төбелердің санын табыңыз ($1$-ші төбенің өзін қоса).",
         "Бірінші жолда $n, m$ ($1 \\le n \\le 10^5$, $0 \\le m \\le 2 \\cdot 10^5$). Келесі $m$ жолда $u, v$ — $u$ төбесінен $v$ төбесіне доға.",
         "Қол жетімді төбелер санын шығарыңыз.",
         ("Бастапқы төбеден шығатын доғалар бойынша жүріңіз.",
          "Алгоритм: енге немесе тереңдікке іздеу (BFS/DFS).",
          "Кезекке 1-ді салу; кезектен u алып, әр v (u -> v) үшін: егер v аралмаған болса белгілеп кезекке салу; аралған төбелер санын шығару"))
def _(r, big):
    n = r.randint(500, 2000) if big else r.randint(2, 8)
    m = r.randint(n // 2, 2 * n) if big else r.randint(0, 8)
    ed = _edges(r, n, m)
    g = _adj(n, ed, directed=True)
    seen = {1}
    dq = deque([1])
    while dq:
        u = dq.popleft()
        for v in g[u]:
            if v not in seen:
                seen.add(v)
                dq.append(v)
    return L(f"{n} {m}", *[f"{u} {v}" for u, v in ed]), L(len(seen))


@problem("Ағаштың диаметрі", ["graphs"], 1700, 4,
         "$n$ төбеден тұратын ағаш берілген. Ағаштың диаметрін — кез келген екі төбе арасындағы ең ұзын жолдағы қабырғалар санын — табыңыз.",
         "Бірінші жолда $n$ ($2 \\le n \\le 10^5$). Келесі $n-1$ жолда $u, v$ — қабырға ұштары.",
         "Диаметрді шығарыңыз.",
         ("Кез келген төбеден ең алыс төбе диаметрдің бір ұшы болады.",
          "Алгоритм: екі рет BFS: алдымен кез келген төбеден, содан соң табылған ең алыс төбеден.",
          "a = BFS(1) ең алыс төбесі; жауап = BFS(a) ең үлкен қашықтығы"))
def _(r, big):
    n = r.randint(500, 3000) if big else r.randint(2, 9)
    ed = _tree_edges(r, n)
    g = _adj(n, ed)

    def bfs(s):
        d = [-1] * (n + 1)
        d[s] = 0
        dq = deque([s])
        while dq:
            u = dq.popleft()
            for v in g[u]:
                if d[v] < 0:
                    d[v] = d[u] + 1
                    dq.append(v)
        far = max(range(1, n + 1), key=lambda x: d[x])
        return far, d[far]

    a, _d = bfs(1)
    return L(n, *[f"{u} {v}" for u, v in ed]), L(bfs(a)[1])


@problem("Минималды қаңқа ағаш", ["graphs"], 1900, 4,
         "$n$ төбе және $m$ қабырғадан тұратын байланыста салмақты бағытсыз граф берілген. "
         "Барлық төбені байланыстыратын қабырғалар жиынының ең аз жиынтық салмағын табыңыз.",
         "Бірінші жолда $n, m$ ($2 \\le n \\le 10^5$, $n-1 \\le m \\le 2 \\cdot 10^5$). Келесі $m$ жолда $u, v, w$ ($1 \\le w \\le 10^6$). Граф байланысты.",
         "Минималды қаңқа ағаштың салмағын шығарыңыз.",
         ("Ең жеңіл қабырғалардан бастап, цикл жасамайтындарын алыңыз.",
          "Алгоритм: Краскал (қабырғаларды сұрыптау + DSU).",
          "Қабырғаларды салмақ бойынша сұрыптау; әр (u, v, w) үшін: егер find(u) != find(v) болса біріктіру және ans += w"))
def _(r, big):
    n = r.randint(300, 1500) if big else r.randint(2, 7)
    ed = [(u, v, r.randint(1, 10**6 if big else 20)) for u, v in _tree_edges(r, n)]
    extra = r.randint(0, 2 * n) if big else r.randint(0, 5)
    for u, v in _edges(r, n, extra):
        ed.append((u, v, r.randint(1, 10**6 if big else 20)))
    r.shuffle(ed)
    par = list(range(n + 1))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    ans = 0
    for u, v, w in sorted(ed, key=lambda e: e[2]):
        ru, rv = find(u), find(v)
        if ru != rv:
            par[ru] = rv
            ans += w
    return L(f"{n} {len(ed)}", *[f"{u} {v} {w}" for u, v, w in ed]), L(ans)


# ============================== build ProblemIn ==============================


def build_all() -> list[tuple[str, ProblemIn]]:
    """Returns [(collection_name, ProblemIn)] in problem-number order. Deterministic."""
    result = []
    for idx, meta in enumerate(_REGISTRY, start=1):
        r = random.Random(idx * 7919)
        subtasks = []
        for big, points in ((False, 40), (True, 60)):
            tests = []
            for k in range(3):
                inp, out = meta["case"](r, big)
                tests.append(TestIn(input=inp, output=out, is_example=(not big and k == 0)))
            subtasks.append(SubtaskIn(points=points, tests=tests))
        statement = (
            f"{meta['desc']}\n\n**Кіріс.** {meta['inp']}\n\n**Шығыс.** {meta['out']}"
        )
        result.append(
            (
                meta["collection"],
                ProblemIn(
                    rating=meta["rating"],
                    time_limit_ms=1000,
                    memory_limit_mb=256,
                    source="OlimpPrep",
                    year=2026,
                    author="OlimpPrep",
                    hide_tags_until_solved=meta["rating"] >= 1500,
                    tags=meta["tags"],
                    translations={"kk": TranslationIn(title=meta["title"], statement=statement)},
                    subtasks=subtasks,
                    hints=[
                        HintIn(level=i + 1, lang="kk", text=text) for i, text in enumerate(meta["hints"])
                    ],
                ),
            )
        )
    return result
