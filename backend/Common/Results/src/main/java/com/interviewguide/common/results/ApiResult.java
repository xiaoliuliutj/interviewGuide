package com.interviewguide.common.results;

import java.util.Objects;

/**
 * Java business API's uniform response.  The response deliberately contains
 * only the status code and the result body; the front end maps failure codes
 * to user-facing wording.
 */
public record ApiResult<T>(int code, T data) {
    public static <T> ApiResult<T> success(T data) {
        return new ApiResult<>(ResultStatus.SUCCESS_WITH_DATA.code(), Objects.requireNonNull(data, "Successful data must not be null"));
    }

    public static <T> ApiResult<T> successWithoutData() {
        return new ApiResult<>(ResultStatus.SUCCESS_WITHOUT_DATA.code(), null);
    }

    public static <T> ApiResult<T> failure(ResultStatus status, T data) {
        if (status.isSuccess()) {
            throw new IllegalArgumentException("Failure response requires a failure status");
        }
        return new ApiResult<>(status.code(), data);
    }

    public static <T> ApiResult<T> failure(ResultStatus status) {
        return failure(status, null);
    }
}
