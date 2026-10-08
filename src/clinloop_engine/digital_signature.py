import hashlib
import json
import os
import secrets
import uuid
import logging
from typing import Any
from .agent_execution import AgentExecutionContext

logger = logging.getLogger("clinloop.digital_signature")

# HMAC-SHA256 signing of agent execution envelopes. The key comes from the
# CLINLOOP_SIGNING_KEY environment variable (use a managed secret in any real
# deployment). A key committed to source control would let anyone forge audit
# signatures, so without the variable a random per-process key is used and
# signatures only verify within the running process.
_env_key = os.environ.get("CLINLOOP_SIGNING_KEY")
SECRET_KEY = _env_key.encode("utf-8") if _env_key else secrets.token_bytes(32)
if not _env_key:
    logger.warning("CLINLOOP_SIGNING_KEY not set; using an ephemeral signing key for this process.")

def sign_agent_context(ctx: AgentExecutionContext) -> str:
    """Signs the AgentExecutionContext, proving provenance and immutability."""
    # Ensure audit fields are populated if they aren't
    if not ctx.inputs_hash:
        ctx.inputs_hash = "missing_input_hash"
    if not ctx.outputs_hash:
        ctx.outputs_hash = "missing_output_hash"
        
    payload = f"{ctx.trace_id}|{ctx.agent_name}|{ctx.inputs_hash}|{ctx.outputs_hash}".encode('utf-8')
    # Use HMAC to simulate the signature
    import hmac
    signature = hmac.new(SECRET_KEY, payload, hashlib.sha256).hexdigest()
    
    logger.debug(f"Signed context {ctx.trace_id} from {ctx.agent_name}")
    return signature

def verify_agent_context(ctx: AgentExecutionContext, signature: str) -> bool:
    """Verifies that the AgentExecutionContext has not been tampered with."""
    payload = f"{ctx.trace_id}|{ctx.agent_name}|{ctx.inputs_hash}|{ctx.outputs_hash}".encode('utf-8')
    import hmac
    expected = hmac.new(SECRET_KEY, payload, hashlib.sha256).hexdigest()
    
    is_valid = hmac.compare_digest(expected, signature)
    if not is_valid:
        logger.error(f"Signature verification FAILED for trace {ctx.trace_id}")
    return is_valid
