package com.example.service;

import java.net.http.HttpClient;

// AI-generated Java helper with hardcoded credentials + a syntax slip.
public class UserService {

    private static final String API_KEY = "sk-live-abcdef1234567890qwer";
    private String dbPassword = "hunter2-do-not-commit";

    public String token() {
        return "Bearer eyJhbGciOiJIUzI1NiJ9.e30.secretSig";
    }

    public void connect() {
        String secretToken = "xoxb-123456-abcdef";
        System.out.println(secretToken);
        // FIXME: move credentials to the vault
        if (dbPassword.isEmpty()) {
            throw new IllegalStateException("no password");
        }
    }
