import re

# ============================================================
# Stage 1 — Deterministic Intent Patterns & Weighted Scoring
# ============================================================

_RE_GREETING = re.compile(
    r"""
    ^
    (
        # English Greetings / Meta
        hi|hello|hey|hiya|howdy|greetings|good\s+(?:morning|afternoon|evening|night)|
        morning|evening|thanks?|thank\s+you|thx|ty|much\s+appreciated|
        who\s+are\s+you|what\s+can\s+you\s+do|how\s+are\s+you|what\s+are\s+you|
        introduce\s+yourself|nice\s+to\s+meet\s+you|good\s+to\s+see\s+you|
        are\s+you\s+there|can\s+you\s+help\s+me|

        # Arabic / Egyptian Greetings / Meta
        مرحبا|مرحباً|مرحبًا|اهلا|اهلاً|أهلا|أهلاً|أهلا\s+بيك|أهلاً\s+بيك|
        اهلا\s+وسهلا|أهلا\s+وسهلا|السلام\s+عليكم|سلام\s+عليكم|وعليكم\s+السلام|
        صباح\s+الخير|مساء\s+الخير|تصبح\s+على\s+خير|ليلة\s+سعيدة|
        شكرا|شكراً|شكرًا|متشكر|متشكرين|تسلم|تسلم\s+يا\s+باشا|ميرسي|
        مين\s+انت|مين\s+إنت|من\s+انت|من\s+إنت|انت\s+مين|إنت\s+مين|
        ماذا\s+تستطيع|ماذا\s+يمكنك|ماذا\s+تفعل|تقدر\s+تعمل\s+ايه|تقدر\s+تعمل\s+إيه|
        بتقدر\s+تعمل\s+ايه|بتقدر\s+تعمل\s+إيه|بتعمل\s+ايه|بتعمل\s+إيه|
        ايه\s+اخبارك|إيه\s+أخبارك|ازيك|إزيك|إزيك\s+عامل\s+ايه|ازيك\s+عامل\s+ايه|
        عامل\s+ايه|عامل\s+إيه|عاملة\s+ايه|عاملة\s+إيه|كيفك|شلونك|كيف\s+حالك|
        اخبارك\s+ايه|أخبارك\s+إيه|كويس|تمام|عامل\s+إيه\s+يا\s+باشا|
        ممكن\s+تساعدني|ممكن\s+تساعدنى|تقدر\s+تساعدني|تقدر\s+تساعدنى|
        انت\s+بتعمل\s+ايه|إنت\s+بتعمل\s+إيه
    )
    [\s!.،؟?]*$
    """,
    re.IGNORECASE | re.VERBOSE,
)


# ============================================================
# SQL Patterns
# Strong = 2 points
# Weak   = 1 point
# ============================================================

_SQL_STRONG = re.compile(
    r"""
    \b(
        # English — Aggregation / Metrics
        how\s+many|how\s+much|count|count\s+of|number\s+of|total|total\s+number|
        sum|sum\s+of|average|avg|mean|median|minimum|maximum|min|max|
        percentage|percent|ratio|rate|growth\s+rate|conversion\s+rate|growth|
        distribution|breakdown|statistics|stats|aggregate|aggregation|

        # English — Analytics / Ranking
        per\s+day|per\s+week|per\s+month|per\s+year|daily|weekly|monthly|yearly|
        year\s+over\s+year|month\s+over\s+month|week\s+over\s+week|
        compare\s+sales|compare\s+revenue|compare\s+orders|top\s+\d+|bottom\s+\d+|
        highest|lowest|most|least|rank|ranking|trend|trends|

        # Arabic — Aggregation / Metrics
        كم|كم\s+عدد|كم\s+واحد|كم\s+واحدة|كام|كام\s+واحد|كام\s+واحدة|
        عدد|عدد\s+من|إجمالي|اجمالي|إجمالي\s+عدد|اجمالي\s+عدد|مجموع|المجموع|
        متوسط|المتوسط|نسبة|نسبه|معدل|معدل\s+النمو|نمو|توزيع|إحصائيات|احصائيات|
        إحصاء|احصاء|حساب|حسابات|مؤشر|مؤشرات|

        # Egyptian Arabic — Questions / Aggregation
        عددهم\s+كام|عددها\s+كام|عددهم\s+قد\s+ايه|عددها\s+قد\s+ايه|
        كام\s+واحد|كام\s+واحدة|كام\s+شخص|كام\s+عميل|كام\s+مستخدم|كام\s+طلب|
        كام\s+أوردر|كام\s+اوردر|كام\s+منتج|كام\s+مرة|كام\s+جنيه|كام\s+فلوس|
        قد\s+ايه|قد\s+إيه|اجمالي\s+كام|إجمالي\s+كام|المجموع\s+كام|
        المتوسط\s+كام|متوسط\s+كام|النسبة\s+كام|النسبة\s+قد\s+ايه|
        المبيعات\s+كام|الإيرادات\s+كام|الايرادات\s+كام|الأرباح\s+كام|الارباح\s+كام|
        التكلفة\s+كام|السعر\s+كام|أعلى\s+كام|اقل\s+كام|أقل\s+كام|
        اكتر\s+كام|أكتر\s+كام|أكبر\s+كام|اصغر\s+كام|أصغر\s+كام|
        اكتر\s+واحد|أكتر\s+واحد|أكتر\s+ناس|أعلى\s+منتج|أعلى\s+عميل|
        أكتر\s+عميل|أكتر\s+منتج|أكتر\s+طلبات|أقل\s+طلبات|

        # Egyptian Arabic — Commands / Requests
        احسب|احسبلي|احسب\s+لي|احسبلي\s+عدد|احسبلي\s+الإجمالي|احسبلي\s+اجمالي|
        احسبلي\s+المتوسط|احسبلي\s+المبيعات|احسبلي\s+الأرباح|
        قولي\s+العدد|قولي\s+عدد|قولي\s+الإجمالي|قولي\s+اجمالي|قولي\s+المتوسط|
        قولي\s+المبيعات|هات\s+العدد|هات\s+الإجمالي|هات\s+اجمالي|هات\s+المتوسط|
        هات\s+المبيعات|طلعلي\s+العدد|طلعلي\s+الإجمالي|طلعلي\s+اجمالي|
        طلعلي\s+المتوسط|وريني\s+العدد|وريني\s+الإجمالي|وريني\s+المتوسط|
        عايز\s+العدد|عايز\s+عدد|عايز\s+اعرف\s+العدد|عايز\s+أعرف\s+العدد|
        عايز\s+اعرف\s+الإجمالي|عايز\s+أعرف\s+الإجمالي|محتاج\s+اعرف\s+العدد|
        محتاج\s+أعرف\s+العدد|فيه\s+كام|في\s+كام|عندي\s+كام|عندنا\s+كام|
        كام\s+عندنا|عايز\s+اعرف\s+كام|عايز\s+أعرف\s+كام
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SQL_WEAK = re.compile(
    r"""
    \b(
        # English — Database Vocabulary
        database|databases|db|sql|query|queries|table|tables|column|columns|
        row|rows|record|records|entry|entries|dataset|datasets|data|schema|schemas|
        database\s+table|data\s+warehouse|data\s+source|

        # English — Business Entities
        user|users|customer|customers|client|clients|account|accounts|order|orders|
        transaction|transactions|payment|payments|invoice|invoices|product|products|
        item|items|sales|sale|revenue|profit|loss|expenses|cost|costs|employee|
        employees|staff|subscription|subscriptions|purchase|purchases|lead|leads|

        # English — Status / Operations
        registered|registration|signed\s+up|signup|signups|logged\s+in|login|
        active|inactive|deleted|created|updated|completed|cancelled|pending|
        failed|successful|status|date|dates|created\s+at|updated\s+at|

        # Arabic — Database Vocabulary
        قاعدة\s+البيانات|قواعد\s+البيانات|بيانات|داتا|جدول|جداول|صف|صفوف|عمود|
        أعمدة|اعمدة|سجل|سجلات|سجلات\s+البيانات|استعلام|استعلامات|استعلام\s+sql|
        قاعدة|داتا\s+بيز|قاعدة\s+داتا|بيانات\s+العملاء|بيانات\s+المستخدمين|

        # Arabic — Business Entities
        مستخدم|مستخدمين|المستخدم|المستخدمين|عميل|عملاء|العملاء|زبون|زبائن|
        حساب|حسابات|طلب|طلبات|الطلبات|أوردر|اوردر|أوردرات|اوردرات|
        معاملة|معاملات|دفعة|دفعات|فاتورة|فواتير|منتج|منتجات|مبيعات|بيع|
        إيرادات|ايرادات|أرباح|ارباح|خسائر|مصروفات|تكلفة|تكاليف|موظف|موظفين|
        اشتراك|اشتراكات|مشتريات|شراء|عملاء|طلبات العملاء|

        # Arabic / Egyptian Status
        مسجل|مسجلين|تسجيل|سجل|سجلوا|اشترك|اشتراك|نشط|نشطة|غير\s+نشط|
        غير\s+نشطة|ملغي|ملغى|ملغية|مكتمل|مكتملة|معلق|معلقة|فشل|ناجح|نجاح|حالة|

        # Egyptian Business Vocabulary
        العميل|العميل\s+بتاع|الزبون|الزبائن|الناس|المستخدمين|اليوزرز|
        الأوردرات|الاوردرات|الأوردر|الاوردر|الفواتير|المنتجات|الحسابات|
        الفلوس|المبيعات|المصاريف|المكسب|المكسبات|الخسارة|الاشتراكات|
        الطلبات|البيانات|الداتا|الجدول|الجداول|السجلات|الصفوف|الأعمدة
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)


# ============================================================
# Retrieval Patterns
# Strong = 2 points
# Weak   = 1 point
# ============================================================

_RETRIEVAL_STRONG = re.compile(
    r"""
    \b(
        # English — Documents / Knowledge
        policy|policies|refund\s+policy|privacy\s+policy|security\s+policy|
        documentation|docs|manual|manuals|terms\s+and\s+conditions|
        terms\s+of\s+service|contract|contracts|agreement|agreements|
        knowledge\s+base|procedure|procedures|regulation|regulations|
        guideline|guidelines|standard|standards|specification|specifications|
        requirements|company\s+policy|internal\s+policy|internal\s+documentation|

        # English — Document Question Intents
        what\s+does\s+the\s+policy\s+say|according\s+to\s+the\s+documentation|
        according\s+to\s+the\s+contract|according\s+to\s+the\s+manual|
        what\s+is\s+our\s+policy|what\s+are\s+the\s+terms|find\s+the\s+policy|
        find\s+the\s+document|look\s+up|search\s+the\s+documents|
        according\s+to\s+company\s+policy|what\s+does\s+the\s+document\s+say|

        # Arabic — Documents / Knowledge
        سياسة|السياسة|سياسات|السياسات|سياسة\s+الخصوصية|سياسة\s+الاسترجاع|
        سياسة\s+الأمان|سياسة\s+الامن|توثيق|التوثيق|دليل|الدليل|أدلة|عقد|العقد|
        عقود|اتفاقية|اتفاقيات|اتفاق|مستند|المستند|مستندات|وثيقة|وثائق|
        لائحة|لوائح|قواعد|إرشادات|ارشادات|متطلبات|مواصفات|معايير|اللوائح|

        # Arabic / Egyptian — Document Questions
        ماذا\s+تقول\s+السياسة|ماذا\s+يقول\s+العقد|حسب\s+التوثيق|حسب\s+المستند|
        حسب\s+الوثيقة|ما\s+هي\s+سياسة|ما\s+هي\s+السياسة|أين\s+أجد\s+السياسة|
        اين\s+اجد\s+السياسة|ابحث\s+عن\s+السياسة|ابحث\s+عن\s+المستند|
        دور\s+على|دور\s+في\s+المستندات|دور\s+في\s+الملفات|

        # Egyptian conversational retrieval
        فين\s+السياسة|فين\s+المستند|فين\s+المعلومة|فين\s+المعلومات|
        موجود\s+فين|موجودة\s+فين|ممكن\s+تدور\s+لي|ممكن\s+تدورلي|
        دورلي\s+على|دور\s+لي\s+على|دورلي\s+في|دور\s+في|
        هاتلي\s+المعلومة|هات\s+المعلومة|طلعلي\s+المعلومة|طلع\s+المعلومة|
        شوف\s+في\s+المستند|شوف\s+في\s+الملفات|راجع\s+المستند|
        راجع\s+السياسة|حسب\s+المستند|حسب\s+الملف|حسب\s+السياسة|
        طبقا\s+للسياسة|طبقاً\s+للسياسة|وفق\s+للسياسة|
        ايه\s+بتقول\s+السياسة|إيه\s+بتقول\s+السياسة|
        السياسة\s+بتقول\s+ايه|السياسة\s+بتقول\s+إيه|
        العقد\s+بيقول\s+ايه|العقد\s+بيقول\s+إيه|
        المستند\s+بيقول\s+ايه|المستند\s+بيقول\s+إيه
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)


_RETRIEVAL_WEAK = re.compile(
    r"""
    \b(
        # English
        guide|guides|how\s+to|tutorial|tutorials|pdf|document|documents|doc|
        file|files|report|reports|faq|faqs|handbook|handbooks|article|articles|
        wiki|knowledge|reference|references|resource|resources|page|pages|
        chapter|section|form|forms|template|templates|read|search|find|lookup|
        information|details|content|material|materials|instructions|

        # Arabic
        تعليمات|تعليم|شرح|طريقة|كيفية|ازاي|إزاي|كيف|دليل|أدلة|ملف|ملفات|
        مستند|مستندات|وثيقة|وثائق|تقرير|تقارير|أسئلة\s+شائعة|اسئلة\s+شائعة|
        كتيب|كتيبات|مقال|مقالات|مرجع|مراجع|مصدر|مصادر|صفحة|صفحات|قسم|أقسام|
        نموذج|نماذج|استمارة|استمارات|ابحث|بحث|دور|معلومة|معلومات|تفاصيل|
        محتوى|محتويات|تعليمات|إرشادات|ارشادات|

        # Egyptian conversational knowledge / retrieval
        اشرحلي|اشرح\s+لي|اشرح|وضحلي|وضح\s+لي|وضح|فهمني|فهمني\s+الموضوع|
        ممكن\s+تشرح|ممكن\s+تشرحلي|ممكن\s+توضح|ممكن\s+توضحلي|
        عايز\s+أفهم|عايز\s+افهم|محتاج\s+أفهم|محتاج\s+افهم|
        عايز\s+أعرف|عايز\s+اعرف|محتاج\s+أعرف|محتاج\s+اعرف|
        قولي\s+عن|قوللي\s+عن|قولي\s+المعلومة|قوللي\s+المعلومة|
        احكيلي\s+عن|احكي\s+لي\s+عن|اديني\s+معلومات|اديني\s+معلومة|
        وريني\s+المستند|وريني\s+الملف|هاتلي\s+الملف|هات\s+الملف|
        فين\s+الملف|فين\s+المستند|فين\s+المعلومة|فين\s+المعلومات|
        ممكن\s+تدور|ممكن\s+تبحث|دورلي|دور\s+لي|ابحثلي|ابحث\s+لي|
        شوف\s+المستند|شوف\s+الملف|راجع\s+الملف|راجع\s+المستند|
        اقرا\s+الملف|اقرأ\s+الملف|اقرا\s+المستند|اقرأ\s+المستند|
        اشرح\s+الموضوع|فهمني\s+الموضوع|الموضوع\s+ده\s+يعني\s+ايه|
        الموضوع\s+ده\s+يعني\s+إيه|يعني\s+ايه|يعني\s+إيه|ايه\s+المقصود|
        إيه\s+المقصود|المقصود\s+ايه|المقصود\s+إيه
    )
    \b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def calculate_deterministic_route(question: str) -> str:
    """
    Calculate deterministic intent using weighted keyword scoring.

    Returns:
        GREETING
        OBVIOUS_SQL
        OBVIOUS_RETRIEVAL
        AMBIGUOUS
    """
    q_stripped = question.strip()

    # --------------------------------------------------------
    # 1. Exact greeting / meta match
    # --------------------------------------------------------
    if _RE_GREETING.fullmatch(q_stripped):
        return "GREETING"

    # --------------------------------------------------------
    # 2. Weighted intent scoring
    # --------------------------------------------------------
    sql_score = len(_SQL_STRONG.findall(question)) * 2 + len(
        _SQL_WEAK.findall(question)
    )

    retrieval_score = len(_RETRIEVAL_STRONG.findall(question)) * 2 + len(
        _RETRIEVAL_WEAK.findall(question)
    )

    # --------------------------------------------------------
    # 3. High-confidence SQL
    # --------------------------------------------------------
    if sql_score >= 2 and sql_score > retrieval_score:
        return "OBVIOUS_SQL"

    # --------------------------------------------------------
    # 4. High-confidence Retrieval
    # --------------------------------------------------------
    if retrieval_score >= 2 and retrieval_score > sql_score:
        return "OBVIOUS_RETRIEVAL"

    # --------------------------------------------------------
    # 5. Ambiguous → fallback classifier
    # --------------------------------------------------------
    return "AMBIGUOUS"
