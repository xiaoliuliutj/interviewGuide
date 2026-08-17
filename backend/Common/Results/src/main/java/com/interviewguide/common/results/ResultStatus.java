package com.interviewguide.common.results;

/**
 * Contract-level status codes.  The first digit identifies the failure owner:
 * 2xx client input, 3xx Java service, and 4xx Python Agent service.
 */
public enum ResultStatus {
    SUCCESS_WITH_DATA(100),
    SUCCESS_WITHOUT_DATA(101),

    INVALID_PARAMETER(200),
    MISSING_PARAMETER(201),
    INVALID_REQUEST_BODY(202),
    INVALID_FILE(203),

    JAVA_INTERNAL_ERROR(300),
    JAVA_BUSINESS_ERROR(301),
    JAVA_DATA_ACCESS_ERROR(302),
    JAVA_RESOURCE_NOT_FOUND(303),

    AGENT_SERVICE_UNAVAILABLE(400),
    AGENT_SERVICE_TIMEOUT(401),
    AGENT_EXECUTION_FAILED(402);

    private final int code;

    ResultStatus(int code) {
        this.code = code;
    }

    public int code() {
        return code;
    }

    public boolean isSuccess() {
        return code == SUCCESS_WITH_DATA.code || code == SUCCESS_WITHOUT_DATA.code;
    }
}
