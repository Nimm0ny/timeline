from fastapi import APIRouter, HTTPException

from backend.app.core.api_errors import API_ERROR_RESPONSES
from backend.app.features import get_feature, list_features
from backend.app.schemas.common import FeatureMapOut, FeatureOut


router = APIRouter(tags=["features"])


@router.get(
    "/api/features",
    response_model=FeatureMapOut,
    operation_id="features_list",
    responses={500: API_ERROR_RESPONSES[500]},
)
def get_features():
    return list_features()


@router.get(
    "/api/features/{feature_id}",
    response_model=FeatureOut,
    operation_id="features_get",
    responses={404: API_ERROR_RESPONSES[404], 500: API_ERROR_RESPONSES[500]},
)
def get_feature_by_id(feature_id: str):
    feature = get_feature(feature_id)
    if feature is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "unknown_feature",
                "message": f"Unknown feature: {feature_id}",
                "nextAction": "List /api/features and choose a registered feature id.",
            },
        )
    return feature
