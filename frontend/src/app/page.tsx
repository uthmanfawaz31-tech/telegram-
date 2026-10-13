"use client";

import React, { useEffect, useState } from "react";
import Background from "@/components/Background";
import FadeIn from "@/components/FadeIn";
import { Shield, Zap, TrendingUp, Key, ArrowRight, CheckCircle2, AlertCircle } from "lucide-react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://telepro-back.onrender.com/api/v1";

export default function Home() {
  const router = useRouter();
  const [phoneNumber, setPhoneNumber] = useState("");
  const [apiId, setApiId] = useState("");
  const [apiHash, setApiHash] = useState("");
  const [otp, setOtp] = useState("");
  const [twoFactorPassword, setTwoFactorPassword] = useState("");
  const [step, setStep] = useState(1); // 1: Credentials & Phone, 2: OTP, 3: 2FA
  const [phoneCodeHash, setPhoneCodeHash] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  useEffect(() => {
    // Pre-populate credentials from localStorage if present
    const savedApiId = localStorage.getItem("tg_api_id");
    const savedApiHash = localStorage.getItem("tg_api_hash");
    const savedPhone = localStorage.getItem("tg_phone");
    if (savedApiId) setApiId(savedApiId);
    if (savedApiHash) setApiHash(savedApiHash);
    if (savedPhone) setPhoneNumber(savedPhone);

    const savedSession = localStorage.getItem("tg_session");
    if (savedSession && savedSession !== "connected") {
      router.push("/dashboard");
      return;
    }

    const checkAccount = async () => {
      try {
        const res = await fetch(`${API_BASE}/telegram/account`);
        if (res.ok) {
          const data = await res.json();
          if (data.is_connected) {
            if (data.account) {
              localStorage.setItem("tg_user", JSON.stringify(data.account));
            }
            router.push("/dashboard");
          }
        }
      } catch (e) {
        // Ignore background probe
      }
    };
    checkAccount();
  }, [router]);

  const handleSendCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setSuccessMsg("");

    if (!phoneNumber.trim()) {
      setError("Please enter your phone number.");
      setLoading(false);
      return;
    }

    // Persist entered credentials immediately
    if (apiId.trim()) localStorage.setItem("tg_api_id", apiId.trim());
    if (apiHash.trim()) localStorage.setItem("tg_api_hash", apiHash.trim());
    localStorage.setItem("tg_phone", phoneNumber.trim());

    try {
      const response = await fetch(`${API_BASE}/telegram/send-code`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phone: phoneNumber.trim(),
          api_id: apiId.trim() || undefined,
          api_hash: apiHash.trim() || undefined,
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Failed to send verification code");
      }

      setPhoneCodeHash(data.phone_code_hash);
      setSuccessMsg("Verification code sent to your Telegram app / SMS!");
      setStep(2);
    } catch (err: any) {
      if (err.message && err.message.includes("Failed to fetch")) {
        setError("Network connection issue: could not reach backend API. If you haven't entered your API ID and Hash, please fill them in below.");
      } else {
        setError(err.message || "Failed to send code. Please verify credentials.");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/telegram/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phone: phoneNumber.trim(),
          code: otp.trim(),
          phone_code_hash: phoneCodeHash,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Invalid verification code");

      if (data.status === "2fa_required") {
        setStep(3);
        setSuccessMsg("Two-Step Verification (2FA) is enabled on this account. Enter your password.");
        return;
      }

      if (data.session_string) {
        localStorage.setItem("tg_session", data.session_string);
      }
      if (data.user) {
        localStorage.setItem("tg_user", JSON.stringify(data.user));
      }
      if (data.api_id || apiId.trim()) {
        localStorage.setItem("tg_api_id", data.api_id || apiId.trim());
      }
      if (data.api_hash || apiHash.trim()) {
        localStorage.setItem("tg_api_hash", data.api_hash || apiHash.trim());
      }
      localStorage.setItem("tg_phone", phoneNumber.trim());

      window.location.href = "/dashboard";
    } catch (err: any) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  const handle2FALogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/telegram/2fa`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phone: phoneNumber.trim(),
          password: twoFactorPassword,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Invalid 2FA password");

      if (data.session_string) {
        localStorage.setItem("tg_session", data.session_string);
      }
      if (data.user) {
        localStorage.setItem("tg_user", JSON.stringify(data.user));
      }
      if (data.api_id || apiId.trim()) {
        localStorage.setItem("tg_api_id", data.api_id || apiId.trim());
      }
      if (data.api_hash || apiHash.trim()) {
        localStorage.setItem("tg_api_hash", data.api_hash || apiHash.trim());
      }
      localStorage.setItem("tg_phone", phoneNumber.trim());

      window.location.href = "/dashboard";
    } catch (err: any) {
      setError(err.message || "2FA verification failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="relative min-h-screen flex flex-col items-center justify-center p-4 overflow-hidden">
      <Background />

      <div className="z-10 w-full max-w-5xl grid grid-cols-1 md:grid-cols-2 gap-10 items-center">
        <FadeIn direction="left">
          <div className="space-y-6">
            <div className="inline-flex items-center px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-sm font-medium">
              <Zap className="w-4 h-4 mr-2" />
              TelePro • Smart Telegram Broadcaster
            </div>
            <h1 className="text-5xl md:text-6xl font-extrabold tracking-tight">
              Scale Your <span className="text-blue-500 text-glow">Reach</span> Safely
            </h1>
            <p className="text-lg text-slate-400 leading-relaxed max-w-lg">
              Broadcast seamlessly to 300+ groups without getting banned. Features automatic group syncing, 1-minute smart timing, humanized typing simulation, and dynamic Spintax templates.
            </p>

            <div className="grid grid-cols-2 gap-4 pt-2">
              <div className="p-4 rounded-xl bg-slate-900/60 border border-white/5 space-y-1">
                <div className="flex items-center space-x-2 text-blue-400 font-semibold text-sm">
                  <Shield className="w-4 h-4" />
                  <span>1-Min Anti-Spam</span>
                </div>
                <p className="text-xs text-slate-400">Natural spacing & typing simulator prevent Telegram limits</p>
              </div>

              <div className="p-4 rounded-xl bg-slate-900/60 border border-white/5 space-y-1">
                <div className="flex items-center space-x-2 text-emerald-400 font-semibold text-sm">
                  <TrendingUp className="w-4 h-4" />
                  <span>Auto Group Sync</span>
                </div>
                <p className="text-xs text-slate-400">Auto-detects newly joined groups & supports 300+ scale</p>
              </div>
            </div>
          </div>
        </FadeIn>

        <FadeIn direction="right" delay={0.2}>
          <div className="blue-glass p-8 md:p-10 rounded-3xl shadow-2xl space-y-6">
            <div>
              <h2 className="text-2xl font-bold text-white">Connect Telegram</h2>
              <p className="text-xs text-slate-400 mt-1">
                {step === 1 && "Enter your phone number & Telegram API credentials to log in"}
                {step === 2 && "Enter the OTP code received in your Telegram app"}
                {step === 3 && "Enter your Two-Step Verification (2FA) password"}
              </p>
            </div>

            {error && (
              <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-3.5 rounded-xl text-xs flex items-start space-x-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            {successMsg && (
              <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 p-3.5 rounded-xl text-xs flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 flex-shrink-0" />
                <span>{successMsg}</span>
              </div>
            )}

            {step === 1 && (
              <form onSubmit={handleSendCode} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Phone Number (with country code)
                  </label>
                  <input
                    type="tel"
                    placeholder="+1 234 567 8900"
                    className="w-full bg-slate-900/80 border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                    value={phoneNumber}
                    onChange={(e) => setPhoneNumber(e.target.value)}
                    required
                    disabled={loading}
                  />
                </div>

                <div className="p-4 rounded-2xl bg-white/5 border border-white/5 space-y-3">
                  <div className="flex items-center space-x-1.5 text-xs font-semibold text-blue-400">
                    <Key className="w-3.5 h-3.5" />
                    <span>Telegram API Credentials</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] font-medium text-slate-400 mb-1">API ID</label>
                      <input
                        type="text"
                        placeholder="e.g. 12345678"
                        className="w-full bg-slate-950 border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                        value={apiId}
                        onChange={(e) => setApiId(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-slate-400 mb-1">API Hash</label>
                      <input
                        type="text"
                        placeholder="e.g. 0123456789abcdef..."
                        className="w-full bg-slate-950 border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-blue-500"
                        value={apiHash}
                        onChange={(e) => setApiHash(e.target.value)}
                      />
                    </div>
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Get your free credentials from <a href="https://my.telegram.org" target="_blank" rel="noreferrer" className="text-blue-400 underline font-medium">my.telegram.org</a> (takes 30 seconds).
                  </p>
                </div>

                <button type="submit" className="btn-primary w-full flex items-center justify-center space-x-2 text-sm py-3" disabled={loading}>
                  <span>{loading ? "Sending Code via Telegram..." : "Send Verification Code"}</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </form>
            )}

            {step === 2 && (
              <form onSubmit={handleLogin} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">Enter Telegram OTP Code</label>
                  <input
                    type="text"
                    placeholder="12345"
                    className="w-full bg-slate-900/80 border border-white/10 rounded-xl px-4 py-3.5 focus:ring-2 focus:ring-blue-500 outline-none transition-all text-white tracking-widest text-lg font-mono text-center"
                    value={otp}
                    onChange={(e) => setOtp(e.target.value)}
                    required
                    disabled={loading}
                    autoFocus
                  />
                  <p className="text-xs text-slate-500 mt-2">Check your Telegram app messages for the login code.</p>
                </div>

                <button type="submit" className="btn-primary w-full text-sm py-3" disabled={loading}>
                  {loading ? "Verifying..." : "Verify & Connect Account"}
                </button>

                <button
                  type="button"
                  onClick={() => { setStep(1); setError(""); }}
                  className="w-full text-xs text-slate-400 hover:text-white transition-colors"
                >
                  Change phone number or credentials
                </button>
              </form>
            )}

            {step === 3 && (
              <form onSubmit={handle2FALogin} className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1.5">2-Step Verification Password</label>
                  <input
                    type="password"
                    placeholder="Enter your 2FA password"
                    className="w-full bg-slate-900/80 border border-white/10 rounded-xl px-4 py-3.5 focus:ring-2 focus:ring-blue-500 outline-none transition-all text-white"
                    value={twoFactorPassword}
                    onChange={(e) => setTwoFactorPassword(e.target.value)}
                    required
                    disabled={loading}
                    autoFocus
                  />
                </div>

                <button type="submit" className="btn-primary w-full text-sm py-3" disabled={loading}>
                  {loading ? "Verifying Password..." : "Submit 2FA & Connect"}
                </button>

                <button
                  type="button"
                  onClick={() => { setStep(2); setError(""); }}
                  className="w-full text-xs text-slate-400 hover:text-white transition-colors"
                >
                  Back to OTP code
                </button>
              </form>
            )}
          </div>
        </FadeIn>
      </div>

      <div className="absolute bottom-6 text-slate-600 text-xs">
        TelePro Telegram Broadcast Platform
      </div>
    </main>
  );
}
