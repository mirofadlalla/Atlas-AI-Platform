class relevance_evaluation_:
    def __init__(self, retrieved_docs, relevant_docs):
        self.retrieved_docs = retrieved_docs
        self.relevant_docs = relevant_docs

    def precision(self):
        true_positives = len(set(self.retrieved_docs) & set(self.relevant_docs))
        false_positives = len(set(self.retrieved_docs) - set(self.relevant_docs))
        if true_positives + false_positives == 0:
            return 0.0
        return true_positives / (true_positives + false_positives)

    def recall(self):
        true_positives = len(set(self.retrieved_docs) & set(self.relevant_docs))
        false_negatives = len(set(self.relevant_docs) - set(self.retrieved_docs))
        if true_positives + false_negatives == 0:
            return 0.0
        return true_positives / (true_positives + false_negatives)

    def mrr(self):
        for rank, doc in enumerate(self.retrieved_docs, start=1):
            if doc in self.relevant_docs:
                return 1.0 / rank
        return 0.0

    def f1_score(self):
        prec = self.precision()
        rec = self.recall()
        if prec + rec == 0:
            return 0.0
        return 2 * (prec * rec) / (prec + rec)
