import os
from enum import Enum

import mlflow
import pendulum
from airflow.decorators import dag, task
from airflow.kubernetes.secret import Secret
from airflow.operators.bash import BashOperator
from airflow.providers.docker.operators.docker import DockerOperator

MLFLOW_TRACKING_URI = "http://mlflow-service.mlflow.svc.cluster.local"  # TODO aus airflow var lesen
EXPERIMENT_NAME = "cnn_skin_cancer"
skin_cancer_container_image = "seblum/cnn-skin-cancer:latest"
secret_name = "airflow-s3-data-bucket-access-credentials"

SECRET_AWS_BUCKET = Secret(deploy_type="env", deploy_target="AWS_BUCKET", secret=secret_name, key="AWS_BUCKET")
SECRET_AWS_REGION = Secret(deploy_type="env", deploy_target="AWS_REGION", secret=secret_name, key="AWS_REGION")
SECRET_AWS_ACCESS_KEY_ID = Secret(
    deploy_type="env",
    deploy_target="AWS_ACCESS_KEY_ID",
    secret=secret_name,
    key="AWS_ACCESS_KEY_ID",
)
SECRET_AWS_SECRET_ACCESS_KEY = Secret(
    deploy_type="env",
    deploy_target="AWS_SECRET_ACCESS_KEY",
    secret=secret_name,
    key="AWS_SECRET_ACCESS_KEY",
)
SECRET_AWS_ROLE_NAME = Secret(
    deploy_type="env",
    deploy_target="AWS_ROLE_NAME",
    secret=secret_name,
    key="AWS_ROLE_NAME",
)


mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)


def make_mlflow():
    try:
        # Creating an experiment
        mlflow_experiment_id = mlflow.create_experiment(EXPERIMENT_NAME)
    except:
        pass
    # Setting the environment with the created experiment
    mlflow_experiment_id = mlflow.set_experiment(EXPERIMENT_NAME).experiment_id
    return mlflow_experiment_id


# when dag is loaded, mlflow experiment is created
mlflow_experiment_id = make_mlflow()


class Model_Class(Enum):
    """This enum includes different models."""

    Basic = "Basic"
    CrossVal = "CrossVal"
    ResNet50 = "ResNet50"


# Set various model params and airflow or environment args


kwargs_env_data = {
    "MLFLOW_TRACKING_URI": MLFLOW_TRACKING_URI,
    "MLFLOW_EXPERIMENT_ID": mlflow_experiment_id,
}

model_params = {
    "num_classes": 2,
    "input_shape": (224, 224, 3),
    "activation": "relu",
    "kernel_initializer_glob": "glorot_uniform",
    "kernel_initializer_norm": "normal",
    "optimizer": "adam",
    "loss": "binary_crossentropy",
    "metrics": ["accuracy"],
    "validation_split": 0.2,
    "epochs": 2,
    "batch_size": 64,
    "learning_rate": 1e-5,
    "pooling": "avg",  # needed for resnet50
    "verbose": 2,
}


@dag(
    "cnn_skin_cancer_k8s_workflow",
    default_args={
        "owner": "seblum",
        "depends_on_past": False,
        "start_date": pendulum.datetime(2021, 1, 1, tz="Europe/Amsterdam"),
        "tags": ["Keras CNN to classify skin cancer"],
    },
    schedule_interval=None,
    max_active_runs=1,
)
def cnn_skin_cancer_workflow():
    @task.kubernetes(
        image=skin_cancer_container_image,
        name="preprocessing",
        namespace="airflow",
        env_vars=kwargs_env_data,
        in_cluster=True,
        get_logs=True,
        do_xcom_push=True,
        # service_account_name="airflow-sa",
        secrets=[
            SECRET_AWS_BUCKET,
            SECRET_AWS_REGION,
            SECRET_AWS_ACCESS_KEY_ID,
            SECRET_AWS_SECRET_ACCESS_KEY,
            SECRET_AWS_ROLE_NAME,
        ],
    )
    def preprocessing_op(mlflow_experiment_id):
        """
        Perform data preprocessing.

        Args:
            mlflow_experiment_id (str): The MLflow experiment ID.

        Returns:
            dict: A dictionary containing the paths to preprocessed data.
        """
        import os
        import time

        time.sleep(60)

        aws_bucket = os.getenv("AWS_BUCKET")

        from src.preprocessing import data_preprocessing

        (
            X_train_data_path,
            y_train_data_path,
            X_test_data_path,
            y_test_data_path,
        ) = data_preprocessing(mlflow_experiment_id=mlflow_experiment_id, aws_bucket=aws_bucket)

        # Create dictionary with S3 paths to return
        return_dict = {
            "X_train_data_path": X_train_data_path,
            "y_train_data_path": y_train_data_path,
            "X_test_data_path": X_test_data_path,
            "y_test_data_path": y_test_data_path,
        }
        return return_dict

    @task.kubernetes(
        image=skin_cancer_container_image,
        namespace="airflow",
        env_vars=kwargs_env_data,
        in_cluster=True,
        get_logs=True,
        do_xcom_push=True,
        secrets=[
            SECRET_AWS_BUCKET,
            SECRET_AWS_REGION,
            SECRET_AWS_ACCESS_KEY_ID,
            SECRET_AWS_SECRET_ACCESS_KEY,
            SECRET_AWS_ROLE_NAME,
        ],
    )
    def model_training_op(mlflow_experiment_id, model_class, model_params, input):
        """
        Train a model.

        Args:
            mlflow_experiment_id (str): The MLflow experiment ID.
            model_class (str): The class of the model to train.
            model_params (dict): A dictionary containing the model parameters.
            input (dict): A dictionary containing the input data.

        Returns:
            dict: A dictionary containing the results of the model training.
        """
        import os

        from src.train import train_model

        aws_bucket = os.getenv("AWS_BUCKET")
        run_id, model_name, model_version, model_stage = train_model(
            mlflow_experiment_id=mlflow_experiment_id,
            model_class=model_class,
            model_params=model_params,
            aws_bucket=aws_bucket,
            import_dict=input,
        )

        return_dict = {
            "run_id": run_id,
            "model_name": model_name,
            "model_version": model_version,
            "model_stage": model_stage,
        }
        return return_dict

    @task.kubernetes(
        image=skin_cancer_container_image,
        name="compare-models",
        namespace="airflow",
        env_vars=kwargs_env_data,
        in_cluster=True,
        get_logs=True,
        do_xcom_push=True,
        secrets=[
            SECRET_AWS_BUCKET,
            SECRET_AWS_REGION,
            SECRET_AWS_ACCESS_KEY_ID,
            SECRET_AWS_SECRET_ACCESS_KEY,
            SECRET_AWS_ROLE_NAME,
        ],
    )
    def compare_models_op(train_data_basic, train_data_resnet50, train_data_crossval):
        """
        Compare trained models.

        Args:
            train_data_basic (dict): A dictionary containing the results of training the basic model.
            train_data_resnet50 (dict): A dictionary containing the results of training the ResNet50 model.
            train_data_crossval (dict): A dictionary containing the results of training the CrossVal model.

        Returns:
            dict: A dictionary containing the results of the model comparison.
        """
        compare_dict = {
            train_data_basic["model_name"]: train_data_basic["run_id"],
            train_data_resnet50["model_name"]: train_data_resnet50["run_id"],
            train_data_crossval["model_name"]: train_data_crossval["run_id"],
        }

        print(compare_dict)
        from src.compare_models import compare_models

        serving_model_name, serving_model_uri, serving_model_version = compare_models(input_dict=compare_dict)
        return_dict = {
            "serving_model_name": serving_model_name,
            "serving_model_uri": serving_model_uri,
            "serving_model_version": serving_model_version,
        }
        return return_dict

    # serve_fastapi_app_op = BashOperator(
    #     task_id="fastapi-serve-app",
    #     bash_command='docker run --detach -p 80:80 -it seblum/model-serving:fastapi-serve-app && echo "fastapi-serve running"',
    # )

    # serve_streamlit_app_op = BashOperator(
    #     task_id="streamlit-inference-app",
    #     bash_command='docker run --detach -p 8501:8501 -it seblum/model-serving:streamlit-inference-app && echo "streamlit-inference running"',
    # )

    # CREATE PIPELINE

    @task
    def test():
        import time

        time.sleep(3600)

    test()
    preprocessed_data = preprocessing_op(
        mlflow_experiment_id=mlflow_experiment_id,
    )
    train_data_basic = model_training_op(
        mlflow_experiment_id=mlflow_experiment_id,
        model_class=Model_Class.Basic.name,
        model_params=model_params,
        input=preprocessed_data,
    )
    train_data_resnet50 = model_training_op(
        mlflow_experiment_id=mlflow_experiment_id,
        model_class=Model_Class.ResNet50.name,
        model_params=model_params,
        input=preprocessed_data,
    )
    train_data_crossval = model_training_op(
        mlflow_experiment_id=mlflow_experiment_id,
        model_class=Model_Class.CrossVal.name,
        model_params=model_params,
        input=preprocessed_data,
    )
    compare_models_dict = compare_models_op(train_data_basic, train_data_resnet50, train_data_crossval)

    # compare_models_dict >> serve_fastapi_app_op >> serve_streamlit_app_op


cnn_skin_cancer_workflow()
