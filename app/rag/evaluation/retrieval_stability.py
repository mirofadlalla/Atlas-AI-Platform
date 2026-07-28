from typing import List , Dict

from ..retrivel_data_pipline import RetrievalPipeline

class retrieval_stability_:
    @staticmethod
    def jaccard_similarity(a: List[str], b: List[str]):
        # Filter out None and empty string IDs
        a_set = {x for x in a if x}
        b_set = {x for x in b if x}
        if not a_set and not b_set:
            return 1.0
        union = a_set | b_set
        if not union:
            return 0.0
        return len(a_set & b_set) / len(union)

    @staticmethod
    def retrieval_stability_test(retriever, question: str, runs: int = 3):
        all_runs = []
        for _ in range(runs):
            retrieved_ = retriever.invoke(question) or []
            retrieved_ids = [doc.metadata.get('id') or doc.metadata.get('_id') for doc in retrieved_]
            all_runs.append([x for x in retrieved_ids if x])
        
        if not all_runs:
            return {"avg_jaccard": 0.0, "runs": []}
        
        base = all_runs[0]
        scores = [retrieval_stability_.jaccard_similarity(base, run) for run in all_runs]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        return {"avg_jaccard": round(avg_score, 4), "runs": all_runs}

    @staticmethod
    def rephrase_stability_test(retriever, question: str, paraphrases: List[str]):
        base_docs = retriever.invoke(question) or []
        base_ids = [x for x in (doc.metadata.get("id") or doc.metadata.get("_id") for doc in base_docs) if x]
        
        if not paraphrases:
            return 1.0
        
        scores = []
        for p in paraphrases:
            p_docs = retriever.invoke(p) or []
            p_ids = [x for x in (doc.metadata.get("id") or doc.metadata.get("_id") for doc in p_docs) if x]
            scores.append(retrieval_stability_.jaccard_similarity(base_ids, p_ids))

        return round(sum(scores) / len(scores), 4) if scores else 0.0