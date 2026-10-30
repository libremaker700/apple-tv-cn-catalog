package com.muyi.primevideo;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Minimal client for the MiniMax Agent "matrix" gateway.
 *
 * Protocol source: reverse engineering of com.minimax.ai 4.22.0
 * (assets/chatcore_android/_next/static/chunks/*.js), bundle modules
 * 63063 (axios interceptors), 49111 (common query params) and
 * 96467 (MD5 implementation). Full write-up:
 * _minimax_reverse/MiniMax-API-清单.md
 *
 * Every request carries three generated headers:
 *   token         - the signed-in user's session token
 *   x-timestamp   - unix seconds
 *   x-signature   - MD5(x-timestamp + SALT + bodyJson)
 *   yy            - MD5(encodeURIComponent(urlWithQuery) + "_" + bodyJson
 *                        + MD5(timestampMillis) + "ooui")
 *
 * Verified against the live gateway: a correctly signed request passes the
 * gateway check (HTTP 200 + base_resp), a tampered x-signature is rejected
 * by the gateway itself (HTTP 400), and a correct signature with a bad token
 * reaches the auth layer (HTTP 401).
 *
 * Use the official open-platform API (https://api.minimaxi.com/v1) for
 * production. This client exists for interop work and for the endpoints the
 * open platform does not expose.
 */
public final class MinimaxMatrixClient {

    /**
     * Domestic production gateway. Note that agent.minimaxi.com redirects
     * here (agent.minimax.cn) as of 2026-10-30; the live web build points at
     * agent.minimax.cn directly.
     */
    public static final String BASE_CN = "https://agent.minimax.cn";
    /** Overseas production gateway (the build we captured used this one). */
    public static final String BASE_GLOBAL = "https://agent.minimax.io";
    /** Account gateway, used for login/refresh. */
    public static final String ACCOUNT_CN = "https://account.minimaxi.com";
    public static final String ACCOUNT_GLOBAL = "https://account.minimax.io";
    /** Host that serves the streaming (SSE) endpoints. */
    public static final String STREAM_BASE = "https://agent-stream.minimax.io";

    /** Client-side salt that the bundle mixes into x-signature. */
    private static final String SALT = "I*7Cf%WZ#S&%1RlZJ&C2";
    private static final String APP_ID = "3001";
    private static final String BIZ_ID = "3";
    private static final String VERSION_CODE = "22201";
    private static final int TIMEOUT_MS = 30_000;

    private final String baseUrl;
    private final String deviceId;
    private final String uuid;
    /** realUserID from the web app's user_detail_agent localStorage entry. */
    private final String userId;
    /** op_ticket from the same entry; the gateway rejects requests without it. */
    private final String opTicket;

    public MinimaxMatrixClient(String baseUrl) {
        this(baseUrl, "0", "");
    }

    /**
     * @param baseUrl  gateway root, e.g. https://agent.minimax.cn
     * @param userId   realUserID (localStorage "user_detail_agent" -> realUserID)
     * @param opTicket op_ticket  (localStorage "user_detail_agent" -> op_ticket)
     */
    public MinimaxMatrixClient(String baseUrl, String userId, String opTicket) {
        this.baseUrl = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        this.deviceId = Long.toString((System.nanoTime() & 0x7fffffffL) + 1_000_0000L);
        this.uuid = UUID.randomUUID().toString();
        this.userId = userId == null ? "0" : userId;
        this.opTicket = opTicket == null ? "" : opTicket;
    }

    public static MinimaxMatrixClient cn() {
        return new MinimaxMatrixClient(BASE_CN);
    }

    public static MinimaxMatrixClient global() {
        return new MinimaxMatrixClient(BASE_GLOBAL);
    }

    /** Client bound to a signed-in session. */
    public static MinimaxMatrixClient cn(String token, String userId, String opTicket) {
        return new MinimaxMatrixClient(BASE_CN, userId, opTicket);
    }

    // ---- signing ---------------------------------------------------------

    private static String md5Hex(String text) throws Exception {
        MessageDigest md5 = MessageDigest.getInstance("MD5");
        byte[] digest = md5.digest(text.getBytes(StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder(digest.length * 2);
        for (byte b : digest) {
            sb.append(Character.forDigit((b >> 4) & 0xf, 16));
            sb.append(Character.forDigit(b & 0xf, 16));
        }
        return sb.toString();
    }

    /** x-signature for a request: MD5(timestampSeconds + SALT + bodyJson). */
    public static String signature(int timestampSeconds, String bodyJson) throws Exception {
        return md5Hex(timestampSeconds + SALT + bodyJson);
    }

    /**
     * yy header for a request:
     * MD5(encodeURIComponent(fullUrlWithQuery) + "_" + bodyJson
     *     + MD5(String(timestampMillis)) + "ooui")
     */
    public static String yyHeader(String fullUrlWithQuery, String bodyJson, long timestampMillis)
            throws Exception {
        return md5Hex(encodeUriComponent(fullUrlWithQuery) + "_" + bodyJson
                + md5Hex(Long.toString(timestampMillis)) + "ooui");
    }

    /** Common query parameters the bundle attaches to every matrix call. */
    private Map<String, String> commonParams(long unixMillis) {
        Map<String, String> p = new LinkedHashMap<>();
        p.put("device_platform", "web");
        p.put("biz_id", BIZ_ID);
        p.put("app_id", APP_ID);
        p.put("version_code", VERSION_CODE);
        p.put("unix", Long.toString(unixMillis));
        p.put("timezone_offset", Integer.toString(-60 * TimeZoneOffsetMinutes()));
        p.put("client", "web");
        p.put("region", "cn");
        p.put("sys_language", "zh");
        p.put("lang", "zh");
        p.put("uuid", uuid);
        p.put("device_id", deviceId);
        p.put("os_name", "Android");
        p.put("browser_name", "chrome");
        p.put("device_memory", "8");
        p.put("cpu_core_num", "8");
        p.put("browser_language", "zh-CN");
        p.put("browser_platform", "Linux armv8l");
        p.put("user_id", userId);
        p.put("op_ticket", opTicket);
        p.put("screen_width", "1920");
        p.put("screen_height", "1080");
        return p;
    }

    private static int TimeZoneOffsetMinutes() {
        return java.util.TimeZone.getDefault().getOffset(System.currentTimeMillis()) / 60000;
    }

    private static String buildQuery(Map<String, String> params) {
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<String, String> e : params.entrySet()) {
            if (sb.length() > 0) {
                sb.append('&');
            }
            sb.append(urlEncode(e.getKey())).append('=').append(urlEncode(e.getValue()));
        }
        return sb.toString();
    }

    /**
     * Query encoding that matches JavaScript's URLSearchParams.toString()
     * (application/x-www-form-urlencoded: space becomes '+', everything else
     * percent-encoded). This must match the bundle byte for byte, because the
     * gateway derives the yy header from the raw query string it receives.
     */
    private static String urlEncode(String raw) {
        try {
            return java.net.URLEncoder.encode(raw, "UTF-8");
        } catch (Exception e) {
            return raw;
        }
    }

    /** Percent-encoding identical to JavaScript's encodeURIComponent. */
    private static String encodeUriComponent(String raw) {
        StringBuilder sb = new StringBuilder();
        byte[] bytes = raw.getBytes(StandardCharsets.UTF_8);
        final String unreserved = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.!~*'()";
        for (byte b : bytes) {
            char c = (char) (b & 0xFF);
            if (unreserved.indexOf(c) >= 0) {
                sb.append(c);
            } else {
                sb.append('%').append(Character.toUpperCase(Character.forDigit((b >> 4) & 0xf, 16)))
                  .append(Character.toUpperCase(Character.forDigit(b & 0xf, 16)));
            }
        }
        return sb.toString();
    }

    // ---- requests --------------------------------------------------------

    /**
     * POST a JSON body to a /matrix/api/v1 path with the gateway signature.
     *
     * @param path    e.g. "/matrix/api/v1/chat/new_session"
     * @param body    request body; serialized exactly as sent
     * @param token   session token, may be null for public endpoints
     * @return parsed response body
     */
    public JSONObject post(String path, JSONObject body, String token) throws Exception {
        return post(path, body, token, null);
    }

    public JSONObject post(String path, JSONObject body, String token, Map<String, String> extraParams)
            throws Exception {
        long unixMs = System.currentTimeMillis();
        int ts = (int) (unixMs / 1000L);
        String bodyJson = body == null ? "" : body.toString();

        Map<String, String> params = commonParams(unixMs);
        if (extraParams != null) {
            params.putAll(extraParams);
        }
        if (token != null && !token.isEmpty()) {
            params.put("token", token);
        }
        String query = buildQuery(params);
        String fullUrl = baseUrl + path + (query.isEmpty() ? "" : "?" + query);

        String signature = md5Hex(ts + SALT + bodyJson);
        String yy = md5Hex(encodeUriComponent(fullUrl) + "_" + bodyJson + md5Hex(Long.toString(unixMs)) + "ooui");

        HttpURLConnection conn = (HttpURLConnection) new URL(fullUrl).openConnection();
        try {
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(TIMEOUT_MS);
            conn.setReadTimeout(TIMEOUT_MS);
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json");
            if (token != null && !token.isEmpty()) {
                conn.setRequestProperty("token", token);
            }
            conn.setRequestProperty("x-timestamp", Integer.toString(ts));
            conn.setRequestProperty("x-signature", signature);
            conn.setRequestProperty("yy", yy);

            byte[] payload = bodyJson.getBytes(StandardCharsets.UTF_8);
            conn.setFixedLengthStreamingMode(payload.length);
            try (OutputStream os = conn.getOutputStream()) {
                os.write(payload);
            }

            int code = conn.getResponseCode();
            InputStream is = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
            String text = is == null ? "" : readAll(is);
            if (code >= 400) {
                throw new MinimaxHttpException(code, text);
            }
            return text.isEmpty() ? new JSONObject() : new JSONObject(text);
        } finally {
            conn.disconnect();
        }
    }

    /** GET a matrix path (used by the file/storage endpoints). */
    public JSONObject get(String path, String token) throws Exception {
        HttpURLConnection conn = (HttpURLConnection) new URL(baseUrl + path).openConnection();
        try {
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(TIMEOUT_MS);
            conn.setReadTimeout(TIMEOUT_MS);
            if (token != null && !token.isEmpty()) {
                conn.setRequestProperty("token", token);
            }
            int code = conn.getResponseCode();
            InputStream is = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
            String text = is == null ? "" : readAll(is);
            if (code >= 400) {
                throw new MinimaxHttpException(code, text);
            }
            return text.isEmpty() ? new JSONObject() : new JSONObject(text);
        } finally {
            conn.disconnect();
        }
    }

    private static String readAll(InputStream is) throws Exception {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = is.read(buf)) > 0) {
            bos.write(buf, 0, n);
        }
        is.close();
        return bos.toString("UTF-8");
    }

    /**
     * Agents available to this account.
     * GET /minimax-cloud/api/v1/agent
     */
    public JSONObject listAgents(String token) throws Exception {
        return get("/minimax-cloud/api/v1/agent", token);
    }

    /**
     * Create a chat session under an agent.
     * POST /minimax-cloud/api/v1/agent/{agentId}/session
     *
     * @return the new session id (the "session_id" field of the response)
     */
    public String createSession(String agentId, String token) throws Exception {
        JSONObject resp = post("/minimax-cloud/api/v1/agent/" + agentId + "/session",
                new JSONObject(), token);
        String id = resp.optString("session_id", "");
        if (id.isEmpty()) {
            throw new MinimaxHttpException(0, "no session_id in create-session response: " + resp);
        }
        return id;
    }

    /** Conversation history of a session. */
    public JSONObject sessionMessages(String sessionId, String token) throws Exception {
        return get("/minimax-cloud/api/v1/session/" + sessionId + "/message", token);
    }

    /**
     * Send a message and stream the reply as server-sent events.
     *
     * POST https://agent-stream.minimax.io/minimax-cloud/api/v1/session/{sessionId}/message
     * body: {"id": sessionId, "content": "..."}
     *
     * The stream emits one JSON object per "data:" line:
     *   {"type":10}                                  stream start
     *   {"type":"query_collapse_view", ...}          turn metadata
     *   {"type":2,  "agent_message":{...}}           user message echo
     *   {"type":6,  "agent_message_chunk":{...}}     chunk (thinking_content / msg_content)
     *
     * @param onEvent receives each raw JSON event payload
     */
    public void sendMessage(String sessionId, String content, String token, EventSink onEvent)
            throws Exception {
        JSONObject body = new JSONObject();
        body.put("id", sessionId);
        body.put("content", content);
        String bodyJson = body.toString();

        long unixMs = System.currentTimeMillis();
        int ts = (int) (unixMs / 1000L);
        String query = buildQuery(commonParams(unixMs));
        String fullUrl = STREAM_BASE + "/minimax-cloud/api/v1/session/" + sessionId + "/message"
                + "?" + query;
        String signature = signature(ts, bodyJson);
        String yy = yyHeader(fullUrl, bodyJson, unixMs);

        HttpURLConnection conn = (HttpURLConnection) new URL(fullUrl).openConnection();
        try {
            conn.setRequestMethod("POST");
            conn.setConnectTimeout(TIMEOUT_MS);
            conn.setReadTimeout(0);           // stream stays open
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setRequestProperty("Accept", "text/event-stream");
            if (token != null && !token.isEmpty()) {
                conn.setRequestProperty("token", token);
            }
            conn.setRequestProperty("x-timestamp", Integer.toString(ts));
            conn.setRequestProperty("x-signature", signature);
            conn.setRequestProperty("yy", yy);

            byte[] payload = bodyJson.getBytes(StandardCharsets.UTF_8);
            conn.setFixedLengthStreamingMode(payload.length);
            try (OutputStream os = conn.getOutputStream()) {
                os.write(payload);
            }

            int code = conn.getResponseCode();
            if (code >= 400) {
                String err = "";
                try (InputStream es = conn.getErrorStream()) {
                    err = es == null ? "" : readAll(es);
                }
                throw new MinimaxHttpException(code, err);
            }
            try (BufferedReader br = new BufferedReader(
                    new InputStreamReader(conn.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = br.readLine()) != null) {
                    if (line.startsWith("data:")) {
                        String payloadText = line.substring(5).trim();
                        if (!payloadText.isEmpty()) {
                            onEvent.onEvent(payloadText);
                        }
                    }
                }
            }
        } finally {
            conn.disconnect();
        }
    }

    /** Callback for streamed SSE payloads. */
    public interface EventSink {
        void onEvent(String jsonPayload);
    }

    // ---- response helpers -------------------------------------------------

    /**
     * Matrix responses wrap failures in base_resp.status_code / status_msg
     * (or statusInfo.code for some endpoints). Returns 0 when the call was
     * accepted.
     */
    public static int statusCode(JSONObject response) {
        if (response == null) {
            return -1;
        }
        JSONObject base = response.optJSONObject("base_resp");
        if (base != null && base.optInt("status_code", 0) != 0) {
            return base.optInt("status_code");
        }
        JSONObject info = response.optJSONObject("statusInfo");
        if (info != null && info.optInt("code", 0) != 0) {
            return info.optInt("code");
        }
        return 0;
    }

    public static String statusMessage(JSONObject response) {
        if (response == null) {
            return "";
        }
        JSONObject base = response.optJSONObject("base_resp");
        if (base != null) {
            return base.optString("status_msg", "");
        }
        JSONObject info = response.optJSONObject("statusInfo");
        if (info != null) {
            return info.optString("statusMsg", info.optString("status_msg", ""));
        }
        return "";
    }

    /** HTTP failure carrying the raw gateway body for inspection. */
    public static final class MinimaxHttpException extends Exception {
        public final int statusCode;
        public final String body;

        MinimaxHttpException(int statusCode, String body) {
            super("HTTP " + statusCode + " " + body);
            this.statusCode = statusCode;
            this.body = body;
        }
    }
}
