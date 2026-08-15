import re

_SHORT_TERM_PATTERNS = re.compile(
    r"""
        \b(
            # English
            it
            |this
            |that
            |these
            |those
            |they
            |them
            |he
            |she
            |the\s+above
            |above
            |previous
            |earlier
            |before
            |mentioned
            |mentioned\s+above
            |as\s+we\s+discussed
            |as\s+mentioned
            |what\s+you\s+said
            |what\s+i\s+said
            |the\s+last\s+answer
            |your\s+last\s+answer
            |my\s+last\s+question

            # Arabic — Standard
            |هذا
            |هذه
            |ذلك
            |تلك
            |هؤلاء
            |هم
            |هما
            |هو
            |هي
            |السابق
            |السابقة
            |سابقا
            |قبل
            |أعلاه
            |المذكور
            |المذكورة
            |المذكور\s+أعلاه

            # Arabic — Egyptian / colloquial
            |ده
            |دي
            |دا
            |دول
            |دولك
            |هم
            |هو
            |هي
            |اللي\s+فات
            |اللي\s+قبل
            |اللي\s+قولته
            |اللي\s+قلته
            |اللي\s+قلت
            |اللي\s+اتكلمنا\s+عليه
            |اللي\s+اتكلمنا\s+فيه
            |اللي\s+فوق
            |السؤال\s+اللي\s+فات
            |الإجابة\s+اللي\s+فاتت
            |كلامك\s+اللي\s+فات
            |زي\s+ما\s+قولت
            |زي\s+ما\s+قلت
            |زي\s+ما\s+اتفقنا
        )\b
        """,
    re.IGNORECASE | re.VERBOSE,
)

# ============================================================
# Semantic Memory
# Stable user-specific facts, preferences, identity, role, etc.
# ============================================================

_SEMANTIC_PATTERNS = re.compile(
    r"""
        \b(
            # English
            my
            |i
            |me
            |mine
            |my\s+name
            |my\s+role
            |my\s+job
            |my\s+work
            |my\s+company
            |my\s+project
            |my\s+projects
            |my\s+preference
            |my\s+preferences
            |my\s+favorite
            |favorite
            |prefer
            |preferred
            |i\s+like
            |i\s+don't\s+like
            |i\s+love
            |i\s+hate
            |i\s+usually
            |i\s+always
            |i\s+work
            |i\s+study
            |where\s+do\s+i\s+work
            |what\s+is\s+my\s+name
            |what\s+do\s+i\s+prefer
            |what\s+do\s+i\s+like
            |what\s+is\s+my\s+role

            # Arabic — Identity / personal facts
            |اسمي
            |أنا
            |انا
            |عندي
            |شغلي
            |وظيفتي
            |دوري
            |شركتي
            |مشروعي
            |مشاريعي
            |تخصصي
            |دراستي
            |جامعتي

            # Arabic — Preferences
            |بحب
            |لا\s+أحب
            |مش\s+بحب
            |مبحبش
            |بفضل
            |أفضل
            |تفضيلي
            |المفضل
            |المفضلة
            |المفضلة\s+عندي
            |ذوقي

            # Arabic — Personal questions
            |ايه\s+اسمي
            |إيه\s+اسمي
            |ما\s+اسمي
            |مين\s+انا
            |من\s+أنا
            |فين\s+شغلي
            |بشتغل\s+فين
            |ايه\s+شغلي
            |إيه\s+شغلي
            |ايه\s+وظيفتي
            |إيه\s+وظيفتي
            |ايه\s+تخصصي
            |إيه\s+تخصصي
            |انا\s+بحب\s+ايه
            |أنا\s+بحب\s+إيه
            |انا\s+بفضل\s+ايه
            |أنا\s+بفضل\s+إيه
        )\b
        """,
    re.IGNORECASE | re.VERBOSE,
)

# ============================================================
# Episodic Memory
# References to previous sessions, past interactions/events.
# ============================================================

_EPISODIC_PATTERNS = re.compile(
    r"""
        \b(
            # English
            last\s+time
            |last\s+session
            |previous\s+session
            |previous\s+conversation
            |previous\s+chat
            |past\s+session
            |past\s+conversation
            |earlier\s+session
            |earlier\s+conversation
            |earlier\s+chat
            |our\s+last\s+conversation
            |our\s+previous\s+conversation
            |when\s+we\s+last\s+talked
            |when\s+we\s+talked\s+before
            |what\s+did\s+we\s+discuss
            |what\s+did\s+i\s+ask
            |what\s+did\s+you\s+tell\s+me
            |yesterday
            |last\s+week
            |last\s+month
            |recently
            |before\s+that
            |earlier\s+today

            # Arabic — Standard
            |المرة\s+السابقة
            |المرة\s+اللي\s+فاتت
            |الجلسة\s+السابقة
            |المحادثة\s+السابقة
            |المحادثة\s+اللي\s+فاتت
            |المحادثة\s+الأخيرة
            |المرة\s+الأخيرة
            |المرة\s+اللي\s+اتكلمنا\s+فيها
            |لما\s+اتكلمنا\s+قبل\s+كده
            |لما\s+اتكلمنا\s+آخر\s+مرة
            |قبل\s+كده
            |من\s+قبل
            |أمس
            |امبارح
            |الأسبوع\s+اللي\s+فات
            |الشهر\s+اللي\s+فات
            |مؤخرا
            |مؤخرًا

            # Arabic — Egyptian
            |آخر\s+مرة
            |اخر\s+مرة
            |آخر\s+جلسة
            |اخر\s+جلسة
            |آخر\s+محادثة
            |اخر\s+محادثة
            |لما\s+اتكلمنا
            |لما\s+كنا\s+بنتكلم
            |كنا\s+بنتكلم\s+عن\s+ايه
            |كنا\s+بنتكلم\s+عن\s+إيه
            |اتكلمنا\s+عن\s+ايه
            |اتكلمنا\s+عن\s+إيه
            |قلتلي\s+ايه
            |قلت\s+لي\s+ايه
            |قولتلي\s+ايه
            |قولت\s+لي\s+ايه
            |انا\s+سألتك\s+عن\s+ايه
            |أنا\s+سألتك\s+عن\s+إيه
        )\b
        """,
    re.IGNORECASE | re.VERBOSE,
)
