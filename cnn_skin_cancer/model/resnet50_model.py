import mlflow
from keras.optimizers import Adam, RMSprop
import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import accuracy_score
from keras.callbacks import ReduceLROnPlateau

# ----- ----- ----- ----- ----- -----
## RESNET 50

def train_resnet50_model(mlflow_tracking_uri:str,mlflow_experiment_id:str, **kwargs):
    mlflow.set_tracking_uri(mlflow_tracking_uri)

    ti = kwargs['ti']

    path_X_train = ti.xcom_pull(key="path_X_train", task_ids='run_preprocessing')
    path_y_train = ti.xcom_pull(key="path_y_train", task_ids='run_preprocessing')
    path_X_test = ti.xcom_pull(key="path_X_test", task_ids='run_preprocessing')
    path_y_test = ti.xcom_pull(key="path_y_test", task_ids='run_preprocessing')

    X_train = np.load(f'{path_X_train}')
    y_train = np.load(f'{path_y_train}')
    X_test = np.load(f'{path_X_test}')
    y_test = np.load(f'{path_y_test}')

    learning_rate_reduction = ReduceLROnPlateau(monitor="accuracy", patience=5, verbose=1, factor=0.5, min_lr=1e-7)

    lr = 1e-5

    params = {
        "num_classes": 2,
        "input_shape": (224, 224, 3),
        "activation": "relu",
        "kernel_initializer": "glorot_uniform",
        "optimizer": "adam",
        "loss": "binary_crossentropy",
        "metrics": ["accuracy"],
        "validation_split": 0.2,
        "epochs": 2,
        "batch_size": 64,
    }

    model = ResNet50(include_top=True, weights=None, input_tensor=None, input_shape=params.get("input_shape"), pooling="avg", classes=params.get("num_classes"))

    model.compile(optimizer=Adam(lr), loss=params.get("loss"), metrics=params.get("metrics"))

    run_name = "resnet50-cnn"
    with mlflow.start_run(experiment_id=mlflow_experiment_id,run_name=run_name) as run:
    
        mlflow.log_params(params)

        history = model.fit(
            X_train,
            y_train,
            validation_split=params.get("validation_split"),
            epochs=params.get("epochs"),
            batch_size=params.get("batch_size"),
            verbose=2,
            callbacks=[learning_rate_reduction],
        )

    # # list all data in history
    # print(history.history.keys())
    # # summarize history for accuracy
    # plt.plot(history.history["acc"])
    # plt.plot(history.history["val_acc"])
    # plt.title("model accuracy")
    # plt.ylabel("accuracy")
    # plt.xlabel("epoch")
    # plt.legend(["train", "test"], loc="upper left")
    # plt.show()
    # # summarize history for loss
    # plt.plot(history.history["loss"])
    # plt.plot(history.history["val_loss"])
    # plt.title("model loss")
    # plt.ylabel("loss")
    # plt.xlabel("epoch")
    # plt.legend(["train", "test"], loc="upper left")
    # plt.show()

    run_name = "resnet50-cnn"
    with mlflow.start_run(experiment_id=mlflow_experiment_id,run_name=run_name) as run:
    
        mlflow.log_params(params)

        # Train ResNet50 on all the data
        model.fit(X_train, y_train, epochs=params.get("epochs"), batch_size=params.get("epochs"), verbose=0, callbacks=[learning_rate_reduction])

    # Testing model on test data to evaluate
    y_pred = model.predict(X_test)
    print(accuracy_score(np.argmax(y_test, axis=1), np.argmax(y_pred, axis=1)))

    mlflow.keras.log_model(model, artifact_path=run_name)

    # save model
    # serialize model to JSON
    resnet50_json = model.to_json()

    with open("resnet50.json", "w") as json_file:
        json_file.write(resnet50_json)

    # serialize weights to HDF5
    model.save_weights("resnet50.h5")
    print("Saved model to disk")
    # 0.8287878787878787
