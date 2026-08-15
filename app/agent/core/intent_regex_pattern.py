import re

# ============================================================
# Stage 1 — Deterministic Intent Patterns & Weighted Scoring
# ============================================================

_RE_GREETING = re.compile(
    r"""
    ^
    (
        # ====================================================
        # English Greetings / Meta
        # ====================================================
        hi
        |hello
        |hey
        |hiya
        |howdy
        |greetings
        |good\s+(?:morning|afternoon|evening|night)
        |morning
        |evening
        |thanks?
        |thank\s+you
        |thx
        |ty
        |much\s+appreciated
        |who\s+are\s+you
        |what\s+can\s+you\s+do
        |how\s+are\s+you
        |what\s+are\s+you
        |introduce\s+yourself

        # ====================================================
        # Arabic Greetings / Meta
        # ====================================================
        |مرحبا
        |مرحباً
        |مرحبًا
        |أهلا
        |أهلاً
        |اهلا
        |اهلاً
        |السلام\s+عليكم
        |سلام\s+عليكم
        |وعليكم\s+السلام
        |صباح\s+الخير
        |مساء\s+الخير
        |تصبح\s+على\s+خير
        |شكرا
        |شكراً
        |شكرًا
        |متشكر
        |متشكرين
        |مين\s+انت
        |مين\s+إنت
        |من\s+انت
        |من\s+إنت
        |ماذا\s+تستطيع
        |ماذا\s+يمكنك
        |ماذا\s+تفعل
        |ازيك
        |إزيك
        |إزيك\s+عامل\s+ايه
        |ازيك\s+عامل\s+ايه
        |كيفك
        |شلونك
        |كيف\s+حالك
        |عامل\s+ايه
        |عاملة\s+ايه
        |ايه\s+اخبارك
        |إيه\s+أخبارك
        |اهلا\s+بيك
        |أهلاً\s+بيك
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
        # ====================================================
        # English — Aggregation / Metrics
        # ====================================================
        how\s+many
        |how\s+much
        |count
        |count\s+of
        |number\s+of
        |total
        |total\s+number
        |sum
        |sum\s+of
        |average
        |avg
        |mean
        |median
        |minimum
        |maximum
        |min
        |max
        |percentage
        |percent
        |ratio
        |rate
        |growth\s+rate
        |conversion\s+rate
        |growth
        |distribution
        |breakdown
        |statistics
        |stats

        # ====================================================
        # English — Time / Analytics
        # ====================================================
        |per\s+day
        |per\s+week
        |per\s+month
        |per\s+year
        |daily
        |weekly
        |monthly
        |yearly
        |year\s+over\s+year
        |month\s+over\s+month
        |week\s+over\s+week
        |compare\s+sales
        |compare\s+revenue
        |top\s+\d+
        |bottom\s+\d+
        |highest
        |lowest
        |most
        |least
        |rank
        |ranking

        # ====================================================
        # Arabic — Aggregation / Metrics
        # ====================================================
        |كم
        |كم\s+عدد
        |كام
        |كام\s+واحد
        |عدد
        |عدد\s+من
        |إجمالي
        |اجمالي
        |إجمالي\s+عدد
        |اجمالي\s+عدد
        |مجموع
        |متوسط
        |المتوسط
        |نسبة
        |نسبه
        |معدل
        |معدل\s+النمو
        |نمو
        |توزيع
        |إحصائيات
        |احصائيات
        |إحصاء
        |احصاء

        # ====================================================
        # Arabic — Analytics
        # ====================================================
        |أعلى
        |اعلى
        |أقل
        |اقل
        |الأعلى
        |الاعلى
        |الأقل
        |الاقل
        |أكثر
        |اكثر
        |أقل\s+عدد
        |ترتيب
        |رتب
        |أفضل
        |افضل
        |أسوأ
        |اسوأ
        |مقارنة
        |قارن
        |تحليل
        |تحليلات
        |تقرير\s+إحصائي
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


_SQL_WEAK = re.compile(
    r"""
    \b(
        # ====================================================
        # English — Database Vocabulary
        # ====================================================
        database
        |databases
        |db
        |sql
        |query
        |queries
        |table
        |tables
        |column
        |columns
        |row
        |rows
        |record
        |records
        |entry
        |entries
        |dataset
        |datasets
        |data
        |schema
        |schemas

        # ====================================================
        # English — Business Entities
        # ====================================================
        user
        |users
        |customer
        |customers
        |client
        |clients
        |account
        |accounts
        |order
        |orders
        |transaction
        |transactions
        |payment
        |payments
        |invoice
        |invoices
        |product
        |products
        |item
        |items
        |sales
        |sale
        |revenue
        |profit
        |loss
        |expenses
        |cost
        |costs
        |employees
        |employee
        |staff
        |subscriptions
        |subscription
        |orders
        |purchases
        |leads
        |customers

        # ====================================================
        # English — Database Operations / Status
        # ====================================================
        |registered
        |registration
        |signed\s+up
        |signup
        |signups
        |logged\s+in
        |login
        |active
        |inactive
        |deleted
        |created
        |updated
        |completed
        |cancelled
        |pending
        |failed
        |successful
        |status

        # ====================================================
        # Arabic — Database Vocabulary
        # ====================================================
        |قاعدة\s+البيانات
        |قواعد\s+البيانات
        |بيانات
        |داتا
        |جدول
        |جداول
        |صف
        |صفوف
        |عمود
        |أعمدة
        |اعمدة
        |سجل
        |سجلات
        |سجلات\s+البيانات
        |استعلام
        |استعلامات
        |استعلام\s+sql
        |قاعدة
        |داتا\s+بيز

        # ====================================================
        # Arabic — Business Entities
        # ====================================================
        |مستخدم
        |مستخدمين
        |المستخدم
        |المستخدمين
        |عميل
        |عملاء
        |العملاء
        |حساب
        |حسابات
        |طلب
        |طلبات
        |الطلبات
        |معاملة
        |معاملات
        |دفعة
        |دفعات
        |فاتورة
        |فواتير
        |منتج
        |منتجات
        |مبيعات
        |بيع
        |إيرادات
        |ايرادات
        |أرباح
        |ارباح
        |خسائر
        |مصروفات
        |تكلفة
        |تكاليف
        |موظف
        |موظفين
        |اشتراك
        |اشتراكات
        |مشتريات

        # ====================================================
        # Arabic — Status / Operations
        # ====================================================
        |مسجل
        |مسجلين
        |تسجيل
        |سجل
        |سجلوا
        |اشترك
        |اشتراك
        |نشط
        |نشطة
        |غير\s+نشط
        |ملغي
        |ملغى
        |مكتمل
        |مكتملة
        |معلق
        |معلقة
        |فشل
        |ناجح
        |نجاح
        |حالة
    )\b
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
        # ====================================================
        # English — Documents / Knowledge
        # ====================================================
        policy
        |policies
        |refund\s+policy
        |privacy\s+policy
        |security\s+policy
        |documentation
        |docs
        |manual
        |manuals
        |terms\s+and\s+conditions
        |terms\s+of\s+service
        |contract
        |contracts
        |agreement
        |agreements
        |knowledge\s+base
        |procedure
        |procedures
        |regulation
        |regulations
        |guideline
        |guidelines
        |standard
        |standards
        |specification
        |specifications
        |requirements
        |company\s+policy
        |internal\s+policy
        |internal\s+documentation

        # ====================================================
        # English — Document Question Intents
        # ====================================================
        |what\s+does\s+the\s+policy\s+say
        |according\s+to\s+the\s+documentation
        |according\s+to\s+the\s+contract
        |according\s+to\s+the\s+manual
        |what\s+is\s+our\s+policy
        |what\s+are\s+the\s+terms
        |find\s+the\s+policy
        |find\s+the\s+document
        |look\s+up
        |search\s+the\s+documents

        # ====================================================
        # Arabic — Documents / Knowledge
        # ====================================================
        |سياسة
        |السياسة
        |سياسات
        |السياسات
        |سياسة\s+الخصوصية
        |سياسة\s+الاسترجاع
        |سياسة\s+الأمان
        |سياسة\s+الأمان
        |توثيق
        |التوثيق
        |دليل
        |الدليل
        |أدلة
        |عقد
        |العقد
        |عقود
        |اتفاقية
        |اتفاقيات
        |اتفاق
        |مستند
        |المستند
        |مستندات
        |وثيقة
        |وثائق
        |لائحة
        |لوائح
        |قواعد
        |إرشادات
        |ارشادات
        |متطلبات
        |مواصفات
        |معايير
        |اللوائح

        # ====================================================
        # Arabic — Document Question Intents
        # ====================================================
        |ماذا\s+تقول\s+السياسة
        |ماذا\s+يقول\s+العقد
        |حسب\s+التوثيق
        |حسب\s+المستند
        |حسب\s+الوثيقة
        |ما\s+هي\s+سياسة
        |ما\s+هي\s+السياسة
        |أين\s+أجد\s+السياسة
        |اين\s+اجد\s+السياسة
        |ابحث\s+عن\s+السياسة
        |ابحث\s+عن\s+المستند
        |دور\s+على
        |دور\s+في\s+المستندات
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


_RETRIEVAL_WEAK = re.compile(
    r"""
    \b(
        # ====================================================
        # English
        # ====================================================
        guide
        |guides
        |how\s+to
        |tutorial
        |tutorials
        |pdf
        |document
        |documents
        |doc
        |file
        |files
        |report
        |reports
        |faq
        |faqs
        |handbook
        |handbooks
        |article
        |articles
        |wiki
        |knowledge
        |reference
        |references
        |resource
        |resources
        |page
        |pages
        |chapter
        |section
        |form
        |forms
        |template
        |templates
        |read
        |search
        |find
        |lookup

        # ====================================================
        # Arabic
        # ====================================================
        |تعليمات
        |تعليم
        |شرح
        |طريقة
        |كيفية
        |ازاي
        |إزاي
        |كيف
        |دليل
        |أدلة
        |ملف
        |ملفات
        |مستند
        |مستندات
        |وثيقة
        |وثائق
        |تقرير
        |تقارير
        |أسئلة\s+شائعة
        |اسئلة\s+شائعة
        |كتيب
        |كتيبات
        |مقال
        |مقالات
        |مرجع
        |مراجع
        |مصدر
        |مصادر
        |صفحة
        |صفحات
        |قسم
        |أقسام
        |نموذج
        |نماذج
        |استمارة
        |استمارات
        |ابحث
        |بحث
        |دور
    )\b
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
