# Security Considerations for WebUI

## Current Status: Development Mode

⚠️ **This WebUI is currently designed for local development and trusted environments only.**

## Known Security Limitations

### 1. No Authentication/Authorization

**Issue**: The `/api/v1/ingest` endpoint is publicly accessible without any authentication.

**Risk**: Anyone with access to the WebUI can:
- Upload arbitrary Markdown content
- Trigger embedding generation (external API calls)
- Write data to the database
- Consume LLM API quota

**Mitigation for Production**:
- [ ] Implement authentication (e.g., session-based, JWT, or API keys)
- [ ] Add authorization checks for ingest operations
- [ ] Rate limiting on ingest endpoint
- [ ] Input validation and sanitization
- [ ] Audit logging for all ingest operations

### 2. CORS Configuration

**Current**: Allows all methods/headers from `http://localhost:5173` (hardcoded)

**Production Recommendations**:
- Use environment variables for allowed origins
- Restrict methods to only what's needed (`GET`, `POST`)
- Add CORS only when needed (consider reverse proxy instead)

### 3. No Input Sanitization

**Current**: Markdown content is accepted as-is and processed

**Recommendations**:
- Add file size limits (backend and frontend)
- Validate Markdown structure
- Sanitize content before database insertion
- Consider content scanning for malicious patterns

## Deployment Checklist

Before deploying to a non-local environment:

- [ ] Add authentication layer (backend + frontend)
- [ ] Configure CORS properly (environment-based)
- [ ] Add rate limiting (per user/IP)
- [ ] Enable HTTPS only
- [ ] Add audit logging
- [ ] Review and restrict ingest permissions
- [ ] Set up monitoring and alerting
- [ ] Document security policies

## Development Best Practices

- Never expose the WebUI on public networks without authentication
- Use environment variables for all configuration
- Keep the `/ingest` endpoint restricted to admin users in production
- Regularly review and update dependencies
