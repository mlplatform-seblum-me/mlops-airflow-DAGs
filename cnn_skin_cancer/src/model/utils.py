from enum import Enum

from keras.models import Model
from src.model.basic_model import BasicNet
from src.model.resnet50_model import ResNet50


class Model_Class(Enum):
    """This enum includes different models."""

    Basic = "Basic"
    CrossVal = "CrossVal"
    ResNet50 = "ResNet50"


def get_model(model_name: str, model_params: dict) -> Model:
    """Get the specified model based on the model name.

    Args:
        model_name (str): The name of the model to retrieve.
        model_params (dict): A dictionary containing the model parameters.

    Returns:
        keras.models.Model: The specified model.

    """
    print(f"name: {model_name}")
    match model_name:
        case Model_Class.Basic.value:
            print("I am here")
            model = BasicNet(model_params)
            print(model)
            # print(model.summary(expand_nested=True))
            model.compile(
                optimizer=model_params.get("optimizer"),
                loss=model_params.get("loss"),
                metrics=model_params.get("metrics"),
            )
            # TODO: doesnt need to print every time
            # print(model.build_graph(model_params).summary())
            return model

        case Model_Class.CrossVal.value:
            pass
        case Model_Class.ResNet50.value:
            model = ResNet50(model_params).call()
            model.compile(
                optimizer=model_params.get("optimizer"),
                loss=model_params.get("loss"),
                metrics=model_params.get("metrics"),
            )
            print(model.summary(expand_nested=True))
            return model
        # TODO: catch case_
