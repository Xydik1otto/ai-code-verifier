package com.example.util;

// Clean Java helper: no secrets, no markers, balanced braces.
public class TokenUtil {

    public String readToken() {
        return System.getenv("APP_TOKEN");
    }

    public boolean isEmpty(String value) {
        return value == null || value.isEmpty();
    }
}
