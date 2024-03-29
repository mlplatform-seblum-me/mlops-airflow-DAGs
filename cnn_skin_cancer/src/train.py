import json
import os
from datetime import datetime
from enum import Enum
from typing import Tuple

import mlflow
import mlflow.keras
import numpy as np
from keras import backend as K
from keras.callbacks import ReduceLROnPlateau
from sklearn.metrics import accuracy_score
from sklearn.model_selection import KFold
from src.model.utils import Model_Class, get_model
from src.utils import AWSSession


def train_model(
    mlflow_experiment_id: str,
    model_class: Enum,
    model_params: dict,
    aws_bucket: str,
    import_dict: dict = {},
) -> Tuple[str, str, int, str]:
    """
    Trains a machine learning model and logs the results to MLflow.

    Args:
        mlflow_experiment_id (str): The ID of the MLflow experiment to log the results.
        model_class (Enum): The class of the model to train.
        model_params (dict): A dictionary containing the parameters for the model.
        aws_bucket (str): The AWS S3 bucket name for data storage.
        import_dict (dict, optional): A dictionary containing paths for importing data. Defaults to {}.

    Returns:
        Tuple[str, str, int, str]: A tuple containing the run ID, model name, model version, and current stage.

    Raises:
        None
    """
    mlflow_tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    mlflow.set_tracking_uri(mlflow_tracking_uri)

    print("\n> Loading data...")
    X_train_data_path = import_dict.get("X_train_data_path")
    y_train_data_path = import_dict.get("y_train_data_path")
    X_test_data_path = import_dict.get("X_test_data_path")
    y_test_data_path = import_dict.get("y_test_data_path")

    # Instantiate aws session based on AWS Access Key
    # AWS Access Key is fetched within AWS Session by os.getenv
    aws_session = AWSSession()
    aws_session.set_sessions()

    # Read NumPy Arrays from S3
    X_train = aws_session.download_npy_from_s3(s3_bucket=aws_bucket, file_key=X_train_data_path)
    y_train = aws_session.download_npy_from_s3(s3_bucket=aws_bucket, file_key=y_train_data_path)
    X_test = aws_session.download_npy_from_s3(s3_bucket=aws_bucket, file_key=X_test_data_path)
    y_test = aws_session.download_npy_from_s3(s3_bucket=aws_bucket, file_key=y_test_data_path)

    print("\n> Training model...")
    print(model_class)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    with mlflow.start_run(experiment_id=mlflow_experiment_id, run_name=f"{timestamp}-{model_class}") as run:
        mlflow.log_params(model_params)
        learning_rate_reduction = ReduceLROnPlateau(monitor="accuracy", patience=5, verbose=1, factor=0.5, min_lr=1e-7)

        # If CrossVal is selected, train BasicNet as Cross-Validated Model
        if model_class == Model_Class.CrossVal.value:
            kfold = KFold(n_splits=3, shuffle=True, random_state=11)
            cvscores = []
            for train, test in kfold.split(X_train, y_train):
                model = get_model(Model_Class.Basic.value, model_params)
                # TODO: autolog kfold ???
                # Train Model
                model.fit(
                    X_train[train],
                    y_train[train],
                    epochs=model_params.get("epochs"),
                    batch_size=model_params.get("batch_size"),
                    verbose=model_params.get("verbose"),
                )
                scores = model.evaluate(X_train[test], y_train[test], verbose=0)
                print("%s: %.2f%%" % (model.metrics_names[1], scores[1] * 100))
                cvscores.append(scores[1] * 100)
                K.clear_session()
        # TODO: not very safe, create if-else on other Enums
        else:
            model = get_model(model_class, model_params)
            mlflow.keras.autolog()
            # Train Model
            model.fit(
                X_train,
                y_train,
                validation_split=model_params.get("validation_split"),
                epochs=model_params.get("epochs"),
                batch_size=model_params.get("batch_size"),
                verbose=model_params.get("verbose"),
                callbacks=[learning_rate_reduction],
            )
            mlflow.keras.autolog(disable=True)

        run_id = run.info.run_id
        model_uri = f"runs:/{run_id}/{model_class}"

        # Testing model on test data to evaluate
        print("\n> Testing model...")
        y_pred = model.predict(X_test)
        prediction_accuracy = accuracy_score(np.argmax(y_test, axis=1), np.argmax(y_pred, axis=1))
        mlflow.log_metric("prediction_accuracy", prediction_accuracy)
        print(f"Prediction Accuracy: {prediction_accuracy}")

        print("\n> Register model...")
        mv = mlflow.register_model(model_uri, model_class)

    return run_id, mv.name, mv.version, mv.current_stage


if __name__ == "__main__":
    mlflow_experiment_id = os.getenv("MLFLOW_EXPERIMENT_ID")
    aws_bucket = os.getenv("AWS_BUCKET")
    model_class = os.getenv("MODEL_CLASS")

    # deleted afterwards
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

    train_model(
        mlflow_experiment_id=mlflow_experiment_id,
        model_class=Model_Class[model_class],
        model_params=model_params,
        aws_bucket=aws_bucket,
    )
