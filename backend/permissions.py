"""
Permission store backed by DynamoDB.

DynamoDB table schema (set DYNAMODB_PERMISSIONS_TABLE env var):
  PK:  user_id (String)        — matches JWT 'sub' claim
       email (String)          — display / audit
       role_arn (String)       — IAM role ARN for STS AssumeRole (Athena/S3)
       allowed_datasets (SS)   — StringSet; absent = no restriction
       allowed_namespaces (SS) — StringSet; absent = no restriction
       is_admin (Boolean)      — bypasses all dataset restrictions

Dev mode (DYNAMODB_PERMISSIONS_TABLE not set): every authenticated user
gets superuser permissions so local development works without AWS.

Example CLI to create the table and seed a user:
  aws dynamodb create-table \
    --table-name rootly-permissions \
    --attribute-definitions AttributeName=user_id,AttributeType=S \
    --key-schema AttributeName=user_id,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST

  aws dynamodb put-item --table-name rootly-permissions --item '{
    "user_id":            {"S": "auth0|abc123"},
    "email":              {"S": "alice@company.com"},
    "role_arn":           {"S": "arn:aws:iam::123456789:role/DataAnalyst"},
    "allowed_datasets":   {"SS": ["orders", "customers", "contratos"]},
    "allowed_namespaces": {"SS": ["s3://prod-bucket/data/"]},
    "is_admin":           {"BOOL": false}
  }'
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from fastapi import Depends, HTTPException

from backend.auth import AuthUser, get_current_user

logger = logging.getLogger(__name__)

PERMISSIONS_TABLE = os.getenv("DYNAMODB_PERMISSIONS_TABLE", "")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "eu-west-1")


@dataclass
class UserPermissions:
    user_id: str
    email: str
    role_arn: Optional[str]
    # None means unrestricted (all datasets / namespaces allowed)
    allowed_datasets: Optional[list[str]]
    allowed_namespaces: Optional[list[str]]
    is_admin: bool = False

    def can_access_dataset(self, dataset_name: str) -> bool:
        if self.is_admin or self.allowed_datasets is None:
            return True
        return dataset_name in self.allowed_datasets

    def can_access_namespace(self, namespace: str) -> bool:
        if self.is_admin or self.allowed_namespaces is None:
            return True
        return namespace in self.allowed_namespaces


def _superuser(user: AuthUser) -> UserPermissions:
    return UserPermissions(
        user_id=user.user_id,
        email=user.email,
        role_arn=None,
        allowed_datasets=None,
        allowed_namespaces=None,
        is_admin=True,
    )


def _dynamo_client():
    return boto3.resource("dynamodb", region_name=AWS_REGION)


def get_permissions(user: AuthUser = Depends(get_current_user)) -> UserPermissions:
    if not PERMISSIONS_TABLE:
        logger.debug("DYNAMODB_PERMISSIONS_TABLE not set — dev mode, returning superuser.")
        return _superuser(user)

    # anonymous in dev mode (JWT_SECRET / JWT_JWKS_URL not set) → superuser
    if user.user_id == "anonymous":
        return _superuser(user)

    try:
        table = _dynamo_client().Table(PERMISSIONS_TABLE)
        resp = table.get_item(Key={"user_id": user.user_id})
        item = resp.get("Item")
    except ClientError as e:
        logger.error(f"DynamoDB lookup failed for user_id={user.user_id}: {e}")
        raise HTTPException(status_code=503, detail="Permission store unavailable.")

    if item is None:
        raise HTTPException(status_code=403, detail="User not authorized.")

    raw_datasets = item.get("allowed_datasets")
    raw_namespaces = item.get("allowed_namespaces")

    return UserPermissions(
        user_id=user.user_id,
        email=item.get("email", user.email),
        role_arn=item.get("role_arn"),
        allowed_datasets=list(raw_datasets) if raw_datasets is not None else None,
        allowed_namespaces=list(raw_namespaces) if raw_namespaces is not None else None,
        is_admin=bool(item.get("is_admin", False)),
    )
