import json
from pathlib import Path
from typing import List, Dict

# Local Imports
from app.rag.retrivel_data_pipline import RetrievalPipeline
from app.rag.evaluation.relevance_evaluation import relevance_evaluation_
from app.rag.evaluation.retrieval_stability import (
    retrieval_stability_ as RetrievalStability,
)


class EvalPipeline:
    def __init__(
        self,
        path: Path,
        tenant_id: str,
        use_reranker: bool = True,
        reranker_strategy: str = "hybrid",
    ):
        self.tenant_id = tenant_id
        self.data = self._get_json_file(path)

        # Initialize RetrievalPipeline with CustomLocalLLM and automatic metric logging
        self.pipeline = RetrievalPipeline(
            tenant_id=tenant_id,
            use_reranker=use_reranker,
            reranker_strategy=reranker_strategy,
        )
        self.retriever = self.pipeline.retriever
        if hasattr(self.retriever, "search_kwargs"):
            self.retriever.search_kwargs[
                "k"
            ] = 10  # Limit to top-2 for evaluation consistency

    def _get_json_file(self, path: Path) -> List[Dict]:
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except Exception as e:
            print(f"[Error] Failed to read JSON: {e}")
            return []

    def _answer_question(self, question: str) -> str:
        """
        Answer question using RetrievalPipeline's ask_stream method.
        Automatically logs metrics, costs, and runs to database.
        """
        full_answer = ""
        # ask_stream yields chunks and automatically handles logging
        for chunk in self.pipeline.ask_stream(question):
            full_answer += chunk
        return full_answer

    @staticmethod
    def _keyword_overlap_score(prediction: str, reference: str) -> float:
        """Simple token F1 between prediction and reference (no external deps)."""
        pred_tokens = set(prediction.lower().split())
        ref_tokens = set(reference.lower().split())
        if not ref_tokens:
            return 0.0
        common = pred_tokens & ref_tokens
        precision = len(common) / len(pred_tokens) if pred_tokens else 0.0
        recall = len(common) / len(ref_tokens)
        if precision + recall == 0:
            return 0.0
        return round(2 * precision * recall / (precision + recall), 4)

    def evaluate(self, runs: int = 2):
        results = []

        for sample in self.data:
            question = sample["question"]
            relevant_docs = [
                str(i)
                for i in sample.get("relevant_ids", sample.get("relevant_docs", []))
            ]
            reference_answer = sample.get("answer", "")

            # --- 1. Retriever Evaluation (Relevance) ---
            retrieved_documents = self.retriever.invoke(question)

            retrieved_ids = [
                str(doc.metadata.get("_id") or doc.metadata.get("id") or "")
                for doc in retrieved_documents
            ]

            rel_eval = relevance_evaluation_(retrieved_ids, relevant_docs)

            # --- 2. Stability Evaluation ---
            stability_scores = RetrievalStability.retrieval_stability_test(
                retriever=self.retriever, question=question, runs=runs
            )

            paraphrases = sample.get("paraphrases", [])
            rephrase_score = None
            if paraphrases:
                rephrase_score = RetrievalStability.rephrase_stability_test(
                    retriever=self.retriever, question=question, paraphrases=paraphrases
                )

            # --- 3. Generator (LLM) Evaluation ---
            # ask_stream automatically logs runs and cost metrics to database
            prediction = self._answer_question(question)
            token_f1 = self._keyword_overlap_score(prediction, reference_answer)

            results.append(
                {
                    "question": question,
                    "retrieval_metrics": {
                        "precision": rel_eval.precision(),
                        "recall": rel_eval.recall(),
                        "f1": rel_eval.f1_score(),
                        "mrr": rel_eval.mrr(),
                    },
                    "stability_metrics": {
                        "avg_jaccard": stability_scores.get("avg_jaccard"),
                        "rephrase_score": rephrase_score,
                    },
                    "generation_metrics": {"token_f1": token_f1},
                    "prediction": prediction,
                    "reference": reference_answer,
                }
            )

        return results


# if __name__ == "__main__":
#     test = EvalPipeline(path=Path("app/rag/evaluation/evaluation_dataset.json"), tenant_id="1234")
#     eval_results = test.evaluate(runs=3)
#     print(json.dumps(eval_results, indent=2))
