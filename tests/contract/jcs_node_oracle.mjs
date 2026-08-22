import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";

const DIGEST_PATTERN = /^sha256:[0-9a-f]{64}$/;
const HEX_PATTERN = /^(?:[0-9a-f]{2})+$/;
const KIND_ERRORS = Object.freeze({
  duplicate_key: "DUPLICATE_KEY",
  float: "FLOAT_FORBIDDEN",
  unsafe_integer: "UNSAFE_INTEGER",
  non_json_number: "NON_JSON_NUMBER",
  top_level_scalar: "TOP_LEVEL_SCALAR",
  lone_surrogate: "LONE_SURROGATE",
  digest_grammar: "DIGEST_GRAMMAR",
});

class OracleError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

function reject(code, message) {
  throw new OracleError(code, message);
}

function requireCondition(condition, code, message) {
  if (!condition) {
    reject(code, message);
  }
}

function requireWellFormedUnicode(value) {
  for (let index = 0; index < value.length; index += 1) {
    const codeUnit = value.charCodeAt(index);
    if (codeUnit >= 0xd800 && codeUnit <= 0xdbff) {
      const nextCodeUnit = value.charCodeAt(index + 1);
      if (!(nextCodeUnit >= 0xdc00 && nextCodeUnit <= 0xdfff)) {
        reject("LONE_SURROGATE", "high surrogate is not followed by a low surrogate");
      }
      index += 1;
    } else if (codeUnit >= 0xdc00 && codeUnit <= 0xdfff) {
      reject("LONE_SURROGATE", "low surrogate is not preceded by a high surrogate");
    }
  }
}

function canonicalizeValue(value) {
  if (value === null) {
    return "null";
  }

  switch (typeof value) {
    case "boolean":
      return value ? "true" : "false";
    case "string":
      requireWellFormedUnicode(value);
      return JSON.stringify(value);
    case "number":
      if (!Number.isFinite(value)) {
        reject("NON_JSON_NUMBER", "NaN and Infinity are outside the JSON number domain");
      }
      if (!Number.isInteger(value)) {
        reject("FLOAT_FORBIDDEN", "floating-point values are forbidden");
      }
      if (!Number.isSafeInteger(value)) {
        reject("UNSAFE_INTEGER", "integer is outside the ECMAScript safe-integer range");
      }
      return JSON.stringify(value);
    case "object":
      if (Array.isArray(value)) {
        return `[${value.map(canonicalizeValue).join(",")}]`;
      }
      return `{${Object.keys(value)
        .sort()
        .map((key) => {
          requireWellFormedUnicode(key);
          return `${JSON.stringify(key)}:${canonicalizeValue(value[key])}`;
        })
        .join(",")}}`;
    default:
      reject("NON_JSON_VALUE", `unsupported JavaScript value type: ${typeof value}`);
  }
}

function canonicalizeDocument(value) {
  if (value === null || typeof value !== "object") {
    reject("TOP_LEVEL_SCALAR", "canonical documents must be an object or array");
  }
  return canonicalizeValue(value);
}

function requireRecord(value, location) {
  requireCondition(
    value !== null && typeof value === "object" && !Array.isArray(value),
    "FIXTURE_SCHEMA",
    `${location} must be an object`,
  );
}

function requireString(value, location) {
  requireCondition(typeof value === "string" && value.length > 0, "FIXTURE_SCHEMA", `${location} must be a non-empty string`);
}

function verifyExpectedRejection(item, parsedInput) {
  const expectedError = KIND_ERRORS[item.kind];
  try {
    canonicalizeDocument(parsedInput);
  } catch (error) {
    if (error instanceof OracleError && error.code === expectedError) {
      return;
    }
    const actualError = error instanceof OracleError ? error.code : error.name;
    reject("NEGATIVE_MISMATCH", `${item.id} expected ${expectedError}, got ${actualError}`);
  }
  reject("NEGATIVE_MISMATCH", `${item.id} was accepted; expected ${expectedError}`);
}

function containsFloatToken(rawJson) {
  let inString = false;
  let escaped = false;
  for (let index = 0; index < rawJson.length; index += 1) {
    const char = rawJson[index];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === '"') {
        inString = false;
      }
      continue;
    }
    if (char === '"') {
      inString = true;
      continue;
    }
    if (char === "-" || (char >= "0" && char <= "9")) {
      const match = rawJson.slice(index).match(/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/);
      if (match !== null) {
        if (match[0].includes(".") || /[eE]/.test(match[0])) {
          return true;
        }
        index += match[0].length - 1;
      }
    }
  }
  return false;
}

function verifyNegative(item) {
  requireRecord(item, "negative item");
  requireString(item.id, "negative.id");
  requireString(item.kind, `${item.id}.kind`);
  requireCondition(Object.hasOwn(KIND_ERRORS, item.kind), "FIXTURE_SCHEMA", `${item.id} has unknown negative kind ${item.kind}`);
  requireCondition(
    item.expected_error === KIND_ERRORS[item.kind],
    "FIXTURE_SCHEMA",
    `${item.id}.expected_error must be ${KIND_ERRORS[item.kind]}`,
  );

  if (item.kind === "duplicate_key") {
    if (Object.hasOwn(item, "input_json")) {
      requireCondition(typeof item.input_json === "string", "FIXTURE_SCHEMA", `${item.id}.input_json must be a string`);
    }
    return;
  }

  if (item.kind === "digest_grammar") {
    requireCondition(Object.hasOwn(item, "value"), "FIXTURE_SCHEMA", `${item.id}.value is required`);
    requireCondition(
      typeof item.value !== "string" || !DIGEST_PATTERN.test(item.value),
      "NEGATIVE_MISMATCH",
      `${item.id}.value unexpectedly satisfies the digest grammar`,
    );
    return;
  }

  requireCondition(typeof item.input_json === "string", "FIXTURE_SCHEMA", `${item.id}.input_json must be a string`);
  if (item.kind === "float" && containsFloatToken(item.input_json)) {
    return;
  }
  let parsedInput;
  try {
    parsedInput = JSON.parse(item.input_json);
  } catch {
    if (item.kind === "non_json_number") {
      return;
    }
    reject("NEGATIVE_MISMATCH", `${item.id} failed JSON parsing before ${KIND_ERRORS[item.kind]} could be checked`);
  }
  verifyExpectedRejection(item, parsedInput);
}

function verifyPositive(vector) {
  requireRecord(vector, "positive vector");
  requireString(vector.id, "positive.id");
  requireCondition(Object.hasOwn(vector, "input"), "FIXTURE_SCHEMA", `${vector.id}.input is required`);
  requireCondition(
    typeof vector.canonical_utf8_hex === "string" && HEX_PATTERN.test(vector.canonical_utf8_hex),
    "FIXTURE_SCHEMA",
    `${vector.id}.canonical_utf8_hex must be non-empty lowercase byte hex`,
  );
  requireCondition(
    typeof vector.sha256 === "string" && DIGEST_PATTERN.test(vector.sha256),
    "FIXTURE_SCHEMA",
    `${vector.id}.sha256 must match sha256:<64 lowercase hex>`,
  );

  const canonicalBytes = Buffer.from(canonicalizeDocument(vector.input), "utf8");
  const actualHex = canonicalBytes.toString("hex");
  requireCondition(actualHex === vector.canonical_utf8_hex, "CANONICAL_BYTES_MISMATCH", `${vector.id} canonical UTF-8 bytes differ`);

  const actualDigest = `sha256:${createHash("sha256").update(canonicalBytes).digest("hex")}`;
  requireCondition(actualDigest === vector.sha256, "DIGEST_MISMATCH", `${vector.id} SHA-256 differs`);
  return canonicalBytes.length;
}

function loadFixture(path) {
  let fixture;
  try {
    fixture = JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    reject("FIXTURE_READ", error instanceof Error ? error.message : String(error));
  }
  requireRecord(fixture, "fixture");
  requireString(fixture.schema_version, "schema_version");
  requireCondition(Array.isArray(fixture.positive), "FIXTURE_SCHEMA", "positive must be an array");
  requireCondition(Array.isArray(fixture.negative), "FIXTURE_SCHEMA", "negative must be an array");
  return fixture;
}

function main() {
  requireCondition(process.argv.length === 3, "USAGE", "node jcs_node_oracle.mjs <fixture.json>");
  const fixture = loadFixture(process.argv[2]);
  const seenIds = new Set();
  let canonicalByteCount = 0;

  for (const vector of fixture.positive) {
    canonicalByteCount += verifyPositive(vector);
    requireCondition(!seenIds.has(vector.id), "FIXTURE_SCHEMA", `duplicate fixture id ${vector.id}`);
    seenIds.add(vector.id);
  }

  const coveredKinds = new Set();
  for (const item of fixture.negative) {
    verifyNegative(item);
    requireCondition(!seenIds.has(item.id), "FIXTURE_SCHEMA", `duplicate fixture id ${item.id}`);
    seenIds.add(item.id);
    coveredKinds.add(item.kind);
  }

  for (const kind of Object.keys(KIND_ERRORS)) {
    requireCondition(coveredKinds.has(kind), "FIXTURE_SCHEMA", `negative fixtures do not cover ${kind}`);
  }

  process.stdout.write(
    `PASS jcs_node_oracle runtime=${process.version} schema_version=${fixture.schema_version} positive=${fixture.positive.length} negative=${fixture.negative.length} canonical_bytes=${canonicalByteCount} float_tokens=raw-lexical duplicate_key=declaration-only\n`,
  );
}

try {
  main();
} catch (error) {
  const code = error instanceof OracleError ? error.code : "UNEXPECTED";
  const message = error instanceof Error ? error.message : String(error);
  process.stderr.write(`FAIL jcs_node_oracle ${code}: ${message}\n`);
  process.exitCode = 1;
}
