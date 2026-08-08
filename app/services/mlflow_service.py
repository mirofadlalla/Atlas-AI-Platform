"""
Service for MLflow integration.

Provides functionality to log model runs, parameters, metrics, and artifacts to MLflow
for experiment tracking and model monitoring.
"""

import logging
from typing import Dict, Any, Optional
import mlflow
from datetime import datetime

logger = logging.getLogger(__name__)


class MLflowService:
    """Service for MLflow experiment tracking and model monitoring."""

    # Default experiment names
    DEFAULT_EXPERIMENT_QUERY = "RAG_Query_Tracking"
    DEFAULT_EXPERIMENT_EVAL = "RAG_Evaluation"
    DEFAULT_EXPERIMENT_INGEST = "RAG_Data_Ingestion"

    @staticmethod
    def initialize_experiment(experiment_name: str) -> str:
        """
        Initialize or get an MLflow experiment.

        Args:
            experiment_name: Name of the experiment

        Returns:
            Experiment ID
        """
        try:
            mlflow.set_experiment(experiment_name)
            experiment = mlflow.get_experiment_by_name(experiment_name)
            if experiment:
                logger.info(f"Using MLflow experiment: {experiment_name}")
                return experiment.experiment_id
        except Exception as e:
            logger.error(f"Error initializing MLflow experiment: {e}")

        return "0"  # Default experiment

    @staticmethod
    def start_run(
        experiment_name: str,
        run_name: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Start a new MLflow run.

        Args:
            experiment_name: Name of the experiment
            run_name: Optional name for the run
            tags: Optional tags for the run

        Returns:
            Run ID
        """
        try:
            MLflowService.initialize_experiment(experiment_name)
            run = mlflow.start_run(run_name=run_name)

            if tags:
                mlflow.set_tags(tags)

            logger.info(f"Started MLflow run: {run.info.run_id}")
            return run.info.run_id

        except Exception as e:
            logger.error(f"Error starting MLflow run: {e}")
            return None

    @staticmethod
    def end_run(status: str = "FINISHED") -> None:
        """
        End the current MLflow run.

        Args:
            status: Run status ('FINISHED', 'FAILED', 'KILLED')
        """
        try:
            mlflow.end_run(status=status)
            logger.info(f"Ended MLflow run with status: {status}")
        except Exception as e:
            logger.error(f"Error ending MLflow run: {e}")

    @staticmethod
    def log_query_run(
        run_id: Optional[str],
        query: str,
        tenant_id: str,
        latency: float,
        cache_hit: bool = False,
        cost_usd: float = 0.0,
        tokens_used: int = 0,
        model_name: str = "Local-LLM",
    ) -> None:
        """
        Log query execution metrics to MLflow.

        Args:
            run_id: Optional MLflow run ID to resume
            query: User query
            tenant_id: Tenant identifier
            latency: Response latency in seconds
            cache_hit: Whether answer came from cache
            cost_usd: Cost in USD
            tokens_used: Number of tokens used
            model_name: Name of the model
        """
        try:
            # End any active run before starting a new one
            active_run = mlflow.active_run()
            if active_run:
                mlflow.end_run()

            if run_id:
                mlflow.start_run(run_id=run_id)
            else:
                MLflowService.initialize_experiment(
                    MLflowService.DEFAULT_EXPERIMENT_QUERY
                )
                mlflow.start_run(
                    run_name=f"query_{tenant_id}_{datetime.utcnow().timestamp()}"
                )

            # Log parameters
            mlflow.log_param("tenant_id", tenant_id)
            mlflow.log_param("model", model_name)
            mlflow.log_param("cache_hit", cache_hit)

            # Log metrics
            mlflow.log_metric("latency_seconds", latency)
            mlflow.log_metric("cost_usd", cost_usd)
            mlflow.log_metric("tokens_used", tokens_used)

            # Log query summary as artifact
            query_summary = {
                "query": query[:500],  # First 500 chars
                "timestamp": datetime.utcnow().isoformat(),
                "cache_hit": cache_hit,
            }
            mlflow.log_dict(query_summary, "query_summary.json")

            logger.info(
                f"Logged query run to MLflow - Query latency: {latency}s, Cost: ${cost_usd}"
            )

        except Exception as e:
            logger.error(f"Error logging query run to MLflow: {e}")
        finally:
            mlflow.end_run()

    @staticmethod
    def log_evaluation_run(
        run_name: str,
        tenant_id: str,
        dataset_size: int,
        num_runs: int,
        metrics: Dict[str, float],
        parameters: Dict[str, Any],
        artifacts: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Log evaluation run to MLflow.

        Args:
            run_name: Name of the evaluation run
            tenant_id: Tenant identifier
            dataset_size: Size of evaluation dataset
            num_runs: Number of evaluation runs
            metrics: Dictionary of metrics to log
            parameters: Dictionary of parameters to log
            artifacts: Dictionary mapping artifact names to file paths

        Returns:
            Run ID
        """
        try:
            MLflowService.initialize_experiment(MLflowService.DEFAULT_EXPERIMENT_EVAL)
            run = mlflow.start_run(run_name=run_name)

            # Log parameters
            mlflow.log_param("tenant_id", tenant_id)
            mlflow.log_param("dataset_size", dataset_size)
            mlflow.log_param("num_runs", num_runs)

            for param_name, param_value in parameters.items():
                mlflow.log_param(f"param_{param_name}", param_value)

            # Log metrics
            for metric_name, metric_value in metrics.items():
                mlflow.log_metric(metric_name, metric_value)

            # Log artifacts
            if artifacts:
                for artifact_name, artifact_path in artifacts.items():
                    try:
                        mlflow.log_artifact(artifact_path, artifact_path.split("/")[-1])
                    except Exception as e:
                        logger.warning(f"Could not log artifact {artifact_name}: {e}")

            logger.info(f"Logged evaluation run to MLflow - Run ID: {run.info.run_id}")
            return run.info.run_id

        except Exception as e:
            logger.error(f"Error logging evaluation run to MLflow: {e}")
            return None
        finally:
            mlflow.end_run()

    @staticmethod
    def log_ingest_run(
        run_name: str,
        tenant_id: str,
        file_path: str,
        documents_count: int,
        chunks_count: int,
        vector_db: str = "Qdrant",
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> str:
        """
        Log data ingestion run to MLflow.

        Args:
            run_name: Name of the ingestion run
            tenant_id: Tenant identifier
            file_path: Path to ingested file
            documents_count: Number of documents processed
            chunks_count: Number of chunks created
            vector_db: Vector database used
            success: Whether ingestion was successful
            error_message: Error message if ingestion failed

        Returns:
            Run ID
        """
        try:
            MLflowService.initialize_experiment(MLflowService.DEFAULT_EXPERIMENT_INGEST)
            run = mlflow.start_run(run_name=run_name)

            # Log parameters
            mlflow.log_param("tenant_id", tenant_id)
            mlflow.log_param("vector_db", vector_db)
            mlflow.log_param("success", success)

            # Log metrics
            mlflow.log_metric("documents_count", documents_count)
            mlflow.log_metric("chunks_count", chunks_count)

            if error_message:
                mlflow.log_param("error_message", error_message)

            # Log file info as artifact
            file_info = {
                "file_path": file_path,
                "timestamp": datetime.utcnow().isoformat(),
                "success": success,
            }
            mlflow.log_dict(file_info, "ingestion_info.json")

            logger.info(
                f"Logged ingestion run to MLflow - Documents: {documents_count}, Chunks: {chunks_count}"
            )
            return run.info.run_id

        except Exception as e:
            logger.error(f"Error logging ingestion run to MLflow: {e}")
            return None
        finally:
            mlflow.end_run()

    @staticmethod
    def log_cost_metrics(
        run_id: Optional[str],
        total_cost_usd: float,
        input_tokens: int,
        output_tokens: int,
        model_name: str,
    ) -> None:
        """
        Log cost-related metrics to MLflow.

        Args:
            run_id: MLflow run ID
            total_cost_usd: Total cost in USD
            input_tokens: Input tokens count
            output_tokens: Output tokens count
            model_name: Model name
        """
        try:
            if run_id:
                mlflow.start_run(run_id=run_id)
            else:
                MLflowService.initialize_experiment(
                    MLflowService.DEFAULT_EXPERIMENT_QUERY
                )
                mlflow.start_run()

            mlflow.log_metric("cost_usd", total_cost_usd)
            mlflow.log_metric("input_tokens", input_tokens)
            mlflow.log_metric("output_tokens", output_tokens)
            mlflow.log_param("model_name", model_name)

            logger.info(
                f"Logged cost metrics to MLflow - Cost: ${total_cost_usd}, "
                f"Tokens: {input_tokens + output_tokens}"
            )

        except Exception as e:
            logger.error(f"Error logging cost metrics: {e}")
        finally:
            mlflow.end_run()

    @staticmethod
    def get_experiment_runs(experiment_name: str) -> list:
        """
        Get all runs for an experiment.

        Args:
            experiment_name: Name of the experiment

        Returns:
            List of run objects
        """
        try:
            experiment = mlflow.get_experiment_by_name(experiment_name)
            if experiment:
                runs = mlflow.search_runs(experiment_ids=[experiment.experiment_id])
                return runs
        except Exception as e:
            logger.error(f"Error retrieving experiment runs: {e}")

        return []
