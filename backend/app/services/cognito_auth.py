"""Cognito JWT Authentication Service.

Supports AWS Cognito Service-to-Service (S2S) authentication using
Client Credentials flow with JWT token verification.
"""

import asyncio
import logging
import time
from typing import Optional
import httpx
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError

logger = logging.getLogger(__name__)


class CognitoAuthService:
    """Service for Cognito JWT authentication and validation."""
    
    def __init__(
        self,
        region: str,
        user_pool_id: str,
        allowed_client_ids: list[str],
        cache_ttl: int = 300,  # Cache JWKS for 5 minutes
    ):
        self.region = region
        self.user_pool_id = user_pool_id
        self.allowed_client_ids = allowed_client_ids
        self.cache_ttl = cache_ttl
        
        # Derived URLs
        self.issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
        self.jwks_url = f"{self.issuer}/.well-known/jwks.json"
        
        # JWKS cache
        self._jwks: Optional[dict] = None
        self._jwks_fetched_at: float = 0
        self._jwks_lock = asyncio.Lock()
    
    async def _get_jwks(self) -> dict:
        """Get JWKS with caching."""
        now = time.time()
        
        # Return cached JWKS if still valid
        if self._jwks and (now - self._jwks_fetched_at) < self.cache_ttl:
            return self._jwks
        
        async with self._jwks_lock:
            # Double-check after acquiring lock
            if self._jwks and (now - self._jwks_fetched_at) < self.cache_ttl:
                return self._jwks
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(self.jwks_url, timeout=10)
                    response.raise_for_status()
                    self._jwks = response.json()
                    self._jwks_fetched_at = time.time()
                    logger.info(f"Fetched JWKS from {self.jwks_url}")
                    return self._jwks
            except Exception as e:
                logger.error(f"Failed to fetch JWKS: {e}")
                # Return stale cache if available
                if self._jwks:
                    logger.warning("Using stale JWKS cache")
                    return self._jwks
                raise
    
    async def verify_token(self, token: str, required_scopes: list[str] | None = None) -> dict:
        """Verify a JWT token from Cognito.

        Args:
            token: The JWT access token to verify
            required_scopes: If provided, all listed scopes must be present in the token

        Returns:
            The decoded token payload if valid

        Raises:
            ValueError: If the token is invalid or verification fails
        """
        try:
            # Get JWKS
            jwks = await self._get_jwks()
            
            # Get unverified headers to find the key ID
            try:
                headers = jwt.get_unverified_headers(token)
            except JWTError as e:
                raise ValueError(f"Invalid token format: {e}")
            
            kid = headers.get("kid")
            if not kid:
                raise ValueError("Token missing key ID (kid)")
            
            # Find the matching key
            key = None
            for k in jwks.get("keys", []):
                if k.get("kid") == kid:
                    key = k
                    break
            
            if not key:
                # JWKS might be outdated, try refreshing
                self._jwks_fetched_at = 0
                jwks = await self._get_jwks()
                for k in jwks.get("keys", []):
                    if k.get("kid") == kid:
                        key = k
                        break
            
            if not key:
                raise ValueError(f"No matching key found for kid: {kid}")
            
            # Verify the token
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self.issuer,
                options={
                    "verify_aud": False,  # S2S tokens don't have audience
                    "verify_exp": True,
                }
            )
            
            # Verify token_use is 'access' for S2S
            token_use = payload.get("token_use")
            if token_use != "access":
                raise ValueError(f"Invalid token_use: {token_use}, expected 'access'")
            
            # Verify client_id if specified
            client_id = payload.get("client_id")
            if self.allowed_client_ids and client_id not in self.allowed_client_ids:
                raise ValueError(f"Client ID {client_id} not in allowed list")

            # Verify required scopes
            if required_scopes:
                token_scopes = set(payload.get("scope", "").split())
                missing = set(required_scopes) - token_scopes
                if missing:
                    raise ValueError(f"Missing required scopes: {', '.join(sorted(missing))}")

            logger.debug(f"Token verified for client: {client_id}")
            return payload
            
        except ExpiredSignatureError:
            raise ValueError("Token has expired")
        except JWTError as e:
            raise ValueError(f"Token verification failed: {e}")
    
    async def create_app_client(self, client_name: str, scopes: list[str]) -> dict:
        """Create a new Cognito app client with client_credentials flow.

        Args:
            client_name: Human-readable name for the client
            scopes: OAuth scopes to grant (e.g. ["openmcpskills-api/mcp"])

        Returns:
            Dict with client_id, client_secret, and metadata
        """
        import aioboto3

        session = aioboto3.Session()
        async with session.client("cognito-idp", region_name=self.region) as client:
            resp = await client.create_user_pool_client(
                UserPoolId=self.user_pool_id,
                ClientName=client_name,
                GenerateSecret=True,
                AllowedOAuthFlows=["client_credentials"],
                AllowedOAuthScopes=scopes,
                AllowedOAuthFlowsUserPoolClient=True,
            )
            app_client = resp["UserPoolClient"]
            return {
                "client_id": app_client["ClientId"],
                "client_secret": app_client.get("ClientSecret", ""),
                "client_name": client_name,
                "scopes": scopes,
            }

    async def get_token_from_credentials(
        self,
        token_endpoint: str,
        client_id: str,
        client_secret: str,
        scopes: list[str],
    ) -> dict:
        """Get a new access token using client credentials.
        
        This is useful for testing or for the server to call other services.
        
        Args:
            token_endpoint: The Cognito token endpoint URL
            client_id: The app client ID
            client_secret: The app client secret
            scopes: List of scopes to request
            
        Returns:
            Token response containing access_token, token_type, expires_in
        """
        import base64
        
        # Create Basic auth header
        credentials = f"{client_id}:{client_secret}"
        auth_header = base64.b64encode(credentials.encode()).decode()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_endpoint,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Basic {auth_header}",
                },
                data={
                    "grant_type": "client_credentials",
                    "scope": " ".join(scopes),
                },
                timeout=10,
            )
            response.raise_for_status()
            return response.json()


# Singleton instance (initialized in main.py)
_cognito_service: Optional[CognitoAuthService] = None


def get_cognito_service() -> Optional[CognitoAuthService]:
    """Get the Cognito auth service instance."""
    return _cognito_service


def set_cognito_service(service: CognitoAuthService) -> None:
    """Set the Cognito auth service instance."""
    global _cognito_service
    _cognito_service = service
