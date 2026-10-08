import hashlib
import json
import uuid
import logging
from typing import Any
from .agent_execution import AgentExecutionContext

logger = logging.getLogger("clinloop.digital_signature")

# In a real ISO 27001 production environment, this would use the cryptography library
# and actual RSA-2048 keys. For the standalone demo environment without extra dependencies,
# we use an HMAC-SHA256 fallback simulating an RSA signature.
SECRET_KEY = b"CLINLOOP_MEDICAL_NOBILITY_SECRET_2026"

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
