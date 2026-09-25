/**
 * The AI stylist prompt bound, mirrored from the API contract.
 *
 * The backend rejects a prompt longer than 2000 characters with 422
 * (`backend/app/schemas/stylist.py::STYLIST_PROMPT_MAX_CHARS`). The input is
 * capped at the same number so a shopper cannot type a request the server will
 * refuse: the limit is a safety default, and a limit a user only discovers by
 * being rejected is a bad one. Kept as a local constant rather than fetched, so
 * the input still works when the API is unreachable.
 *
 * ENGINEERING SAFETY DEFAULT — not a product requirement. See the schema comment:
 * production prompts have a measured maximum of 240 characters.
 */
export const STYLIST_PROMPT_MAX_CHARS = 2000;
