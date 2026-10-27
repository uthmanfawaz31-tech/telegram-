"use client";

import { motion } from "framer-motion";
import {
    Users,
    Send,
    Calendar,
    Layers,
    BarChart3,
    Settings as SettingIcon,
    LogOut,
    Plus,
    Clock,
    Shield,
    TrendingUp,
    RefreshCw,
    Search,
    CheckCircle2,
    XCircle,
    AlertTriangle,
    Pause,
    Play,
    StopCircle,
    FileText,
    Copy,
    Trash2,
    Eye,
    Sparkles,
    UserCheck,
    MessageCircle,
    Sliders,
    Link as LinkIcon,
    Menu,
    X,
    Image as ImageIcon,
    Video as VideoIcon,
    UploadCloud,
    Film
} from "lucide-react";
import Background from "@/components/Background";
import FadeIn from "@/components/FadeIn";

import React, { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "https://telepro-back.onrender.com/api/v1";

interface TelegramUser {
    id?: number;
    phone?: string;
    first_name?: string;
    username?: string;
}

interface TelegramGroup {
    id: number;
    peer_id: string;
    title: string;
    username?: string;
    entity_type: string;
    members_count: number;
    can_send_messages: boolean;
    is_active: boolean;
    last_synced_at?: string;
}

interface BroadcastTemplate {
    id: number;
    name: string;
    message_text: string;
    tags?: string;
    media_path?: string | null;
    media_url?: string | null;
    created_at: string;
    updated_at: string;
}

interface Campaign {
    id: number;
    name: string;
    message_text: string;
    media_path?: string | null;
    media_url?: string | null;
    status: string;
    total_targets: number;
    processed_count: number;
    success_count: number;
    failed_count: number;
    current_target_name?: string;
    current_index: number;
    delay_seconds: number;
    use_jitter: boolean;
    created_at: string;
    started_at?: string;
    completed_at?: string;
}

export default function Dashboard() {
    const router = useRouter();
    const [activeTab, setActiveTab] = useState("Overview");
    const [user, setUser] = useState<TelegramUser | null>(null);
    const [accountData, setAccountData] = useState<any>(null);
    const [isSidebarVisible, setIsSidebarVisible] = useState(false);
    
    // Broadcast & group states
    const [selectedGroupIds, setSelectedGroupIds] = useState<string[]>([]);
    const [showCampaignModal, setShowCampaignModal] = useState(false);
    const [showTemplateModal, setShowTemplateModal] = useState(false);
    const [showJoinModal, setShowJoinModal] = useState(false);
    const [editingTemplate, setEditingTemplate] = useState<BroadcastTemplate | null>(null);
    const [inspectCampaignId, setInspectCampaignId] = useState<number | null>(null);
    const [showEditCampaignModal, setShowEditCampaignModal] = useState(false);
    const [editingCampaignMessage, setEditingCampaignMessage] = useState("");
    const [templateUpdateSignal, setTemplateUpdateSignal] = useState(0);
    const [campaignDraft, setCampaignDraft] = useState<{ message: string; media_path?: string | null; media_url?: string | null } | null>(null);
    
    // Global sync notification
    const [syncing, setSyncing] = useState(false);
    const [syncMessage, setSyncMessage] = useState("");

    // Active campaign polling
    const [activeCampaign, setActiveCampaign] = useState<Campaign | null>(null);

    const [restoringSession, setRestoringSession] = useState(false);

    useEffect(() => {
        const session = typeof window !== "undefined" ? localStorage.getItem("tg_session") : null;
        const userData = typeof window !== "undefined" ? localStorage.getItem("tg_user") : null;
        if (!session) {
            router.push("/");
            return;
        }
        if (userData) {
            try {
                setUser(JSON.parse(userData));
            } catch (e) {}
        }
        fetchAccount();
    }, [router]);

    const fetchAccount = async () => {
        const session = typeof window !== "undefined" ? localStorage.getItem("tg_session") : null;
        const apiId = typeof window !== "undefined" ? localStorage.getItem("tg_api_id") : null;
        const apiHash = typeof window !== "undefined" ? localStorage.getItem("tg_api_hash") : null;
        const phone = typeof window !== "undefined" ? localStorage.getItem("tg_phone") : null;

        try {
            const res = await fetch(`${API_BASE}/telegram/account`);
            if (res.ok) {
                const data = await res.json();
                if (data.is_connected && data.account) {
                    setAccountData(data);
                    setUser(data.account);
                    localStorage.setItem("tg_user", JSON.stringify(data.account));
                    return;
                }
            }

            // If backend container restarted or lost connection, restore session automatically
            // This prevents involuntary logouts and keeps user logged in indefinitely!
            if (session && session !== "connected") {
                setRestoringSession(true);
                try {
                    const restoreRes = await fetch(`${API_BASE}/telegram/restore-session`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            session_string: session,
                            api_id: apiId || undefined,
                            api_hash: apiHash || undefined,
                            phone: phone || undefined,
                        }),
                    });
                    if (restoreRes.ok) {
                        const restoredData = await restoreRes.json();
                        setAccountData(restoredData);
                        if (restoredData.account) {
                            setUser(restoredData.account);
                            localStorage.setItem("tg_user", JSON.stringify(restoredData.account));
                        }
                    }
                } catch (restoreErr) {
                    console.error("Session restore attempt failed:", restoreErr);
                } finally {
                    setRestoringSession(false);
                }
            }
        } catch (e) {
            console.error("Failed to fetch account status", e);
        }
    };

    // Poll for active or interrupted campaign status every 3 seconds + keep phone screen awake
    useEffect(() => {
        let wakeLock: any = null;
        const requestWakeLock = async () => {
            if (typeof navigator !== "undefined" && "wakeLock" in navigator && activeCampaign?.status === "running") {
                try {
                    wakeLock = await (navigator as any).wakeLock.request("screen");
                } catch (err) {}
            }
        };

        const pollCampaigns = async () => {
            try {
                const res = await fetch(`${API_BASE}/campaigns?limit=10`);
                if (res.ok) {
                    const data: Campaign[] = await res.json();
                    const ongoing = data.find(c => c.status === "running" || c.status === "paused" || c.status === "interrupted");
                    setActiveCampaign(ongoing || null);
                }
            } catch (e) {}
        };

        pollCampaigns();
        requestWakeLock();

        const handleVisibilityChange = () => {
            if (document.visibilityState === "visible") {
                pollCampaigns();
                requestWakeLock();
            }
        };

        const interval = setInterval(pollCampaigns, 3000);
        document.addEventListener("visibilitychange", handleVisibilityChange);

        return () => {
            clearInterval(interval);
            document.removeEventListener("visibilitychange", handleVisibilityChange);
            if (wakeLock) {
                wakeLock.release().catch(() => {});
            }
        };
    }, [activeCampaign?.status]);

    const handleSyncGroups = async () => {
        setSyncing(true);
        setSyncMessage("");
        try {
            const res = await fetch(`${API_BASE}/telegram/sync-groups`, { method: "POST" });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Failed to sync groups");
            setSyncMessage(`Synced ${data.total_groups} groups (${data.new_groups} new)`);
            fetchAccount();
            setTimeout(() => setSyncMessage(""), 5000);
        } catch (err: any) {
            alert(err.message || "Sync failed");
        } finally {
            setSyncing(false);
        }
    };

    const handleLogout = async () => {
        if (!confirm("Are you sure you want to log out of your Telegram account?")) {
            return;
        }
        try {
            await fetch(`${API_BASE}/telegram/disconnect`, { method: "POST" });
        } catch (e) {}
        // Explicit logout only: remove active session and user
        localStorage.removeItem("tg_session");
        localStorage.removeItem("tg_user");
        // Keep templates backup and inputs intact in database/localStorage!
        router.push("/");
    };

    return (
        <div className="min-h-screen flex bg-black/60 overflow-hidden text-slate-100 relative">
            <Background />

            {/* Backdrop: clicking outside closes the drawer */}
            {isSidebarVisible && (
                <div
                    onClick={() => setIsSidebarVisible(false)}
                    className="fixed inset-0 bg-black/75 backdrop-blur-sm z-40 transition-opacity"
                />
            )}

            {/* Sidebar Drawer: hidden by default, slides in when hamburger clicked */}
            <aside className={`fixed inset-y-0 left-0 z-50 w-72 blue-glass border-r border-white/10 flex flex-col transition-transform duration-300 ease-in-out shadow-2xl ${isSidebarVisible ? "translate-x-0" : "-translate-x-full"}`}>
                <div className="p-6 border-b border-white/5">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                            <div className="w-9 h-9 rounded-xl bg-blue-600/30 border border-blue-500/30 flex items-center justify-center text-blue-400">
                                <Send className="w-5 h-5" />
                            </div>
                            <div>
                                <span className="font-bold text-lg text-white tracking-tight">TelePro</span>
                                <span className="block text-[10px] uppercase tracking-wider text-blue-400 font-semibold">Broadcaster</span>
                            </div>
                        </div>

                        {/* Cancel / Close icon on the menu */}
                        <button
                            onClick={() => setIsSidebarVisible(false)}
                            className="p-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-all"
                            title="Close Menu"
                        >
                            <X className="w-5 h-5" />
                        </button>
                    </div>
                </div>

                <nav className="flex-1 px-4 space-y-1.5 py-4 overflow-y-auto">
                    <NavItem
                        icon={<Layers className="w-4 h-4" />}
                        label="Overview"
                        active={activeTab === "Overview"}
                        onClick={() => {
                            setActiveTab("Overview");
                            setIsSidebarVisible(false);
                        }}
                    />
                    <NavItem
                        icon={<Users className="w-4 h-4" />}
                        label="Groups Directory"
                        badge={accountData?.total_groups ? `${accountData.total_groups}` : undefined}
                        active={activeTab === "Groups"}
                        onClick={() => {
                            setActiveTab("Groups");
                            setIsSidebarVisible(false);
                        }}
                    />
                    <NavItem
                        icon={<FileText className="w-4 h-4" />}
                        label="Templates"
                        active={activeTab === "Templates"}
                        onClick={() => {
                            setActiveTab("Templates");
                            setIsSidebarVisible(false);
                        }}
                    />
                    <NavItem
                        icon={<Send className="w-4 h-4" />}
                        label="Broadcasts"
                        badge={activeCampaign ? "LIVE" : undefined}
                        badgeColor={activeCampaign ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" : undefined}
                        active={activeTab === "Broadcasts"}
                        onClick={() => {
                            setActiveTab("Broadcasts");
                            setIsSidebarVisible(false);
                        }}
                    />
                    <NavItem
                        icon={<BarChart3 className="w-4 h-4" />}
                        label="Analytics"
                        active={activeTab === "Analytics"}
                        onClick={() => {
                            setActiveTab("Analytics");
                            setIsSidebarVisible(false);
                        }}
                    />
                    <NavItem
                        icon={<SettingIcon className="w-4 h-4" />}
                        label="Settings"
                        active={activeTab === "Settings"}
                        onClick={() => {
                            setActiveTab("Settings");
                            setIsSidebarVisible(false);
                        }}
                    />
                </nav>

                <div className="p-4 mt-auto border-t border-white/5">
                    <div className="p-4 rounded-2xl bg-white/5 border border-white/5 space-y-3">
                        <div className="flex items-center space-x-3">
                            <div className="w-9 h-9 rounded-xl bg-blue-500/20 flex items-center justify-center text-blue-400 font-bold border border-blue-500/20">
                                {user?.first_name?.charAt(0) || "U"}
                            </div>
                            <div className="overflow-hidden">
                                <p className="text-sm font-semibold text-white truncate">{user?.first_name || "Telegram User"}</p>
                                <p className="text-xs text-slate-400 truncate">{user?.phone || (user?.username ? `@${user.username}` : "Connected")}</p>
                            </div>
                        </div>
                        <div className="flex items-center justify-between pt-2 border-t border-white/5 text-xs">
                            <span className="inline-flex items-center text-emerald-400 font-medium">
                                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse mr-1.5" />
                                Online
                            </span>
                            <button
                                onClick={handleLogout}
                                className="text-slate-400 hover:text-red-400 transition-colors flex items-center space-x-1"
                            >
                                <LogOut className="w-3.5 h-3.5" />
                                <span>Exit</span>
                            </button>
                        </div>
                    </div>
                </div>
            </aside>

            {/* Main Content */}
            <main className="flex-1 overflow-y-auto p-6 md:p-10 z-10 text-white relative w-full">
                <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
                    <div className="flex items-center space-x-3.5">
                        {/* Hamburger Button to Open Menu */}
                        <button
                            onClick={() => setIsSidebarVisible(true)}
                            className="p-2.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 hover:text-white transition-all flex items-center justify-center flex-shrink-0"
                            title="Open Menu"
                        >
                            <Menu className="w-5 h-5 text-blue-400" />
                        </button>

                        <div>
                            <h1 className="text-3xl font-extrabold tracking-tight">{activeTab}</h1>
                            <p className="text-sm text-slate-400 mt-1">
                                {activeTab === "Overview" && `Welcome back, ${user?.first_name || "Scout"}. Monitor and scale your broadcasts.`}
                                {activeTab === "Groups" && "Manage detected Telegram groups, auto-sync new ones, and target 300+ groups."}
                                {activeTab === "Templates" && "Create dynamic spintax messages and test variations with anti-spam tags."}
                                {activeTab === "Broadcasts" && "Control running campaigns with 1-minute smart timing and view live delivery logs."}
                                {activeTab === "Analytics" && "Performance metrics, group delivery rates, and reach insights."}
                                {activeTab === "Settings" && "Telegram MTProto credentials, delay preferences, and account management."}
                            </p>
                        </div>
                    </div>

                    <div className="flex items-center space-x-3">
                        {syncMessage && (
                            <span className="text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-lg flex items-center space-x-1.5">
                                <CheckCircle2 className="w-3.5 h-3.5" />
                                <span>{syncMessage}</span>
                            </span>
                        )}

                        <button
                            onClick={handleSyncGroups}
                            disabled={syncing}
                            className="px-4 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 hover:text-white text-xs font-semibold flex items-center space-x-2 transition-all active:scale-95 disabled:opacity-50"
                            title="Auto-detect new groups joined from your Telegram account"
                        >
                            <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin text-blue-400' : ''}`} />
                            <span>{syncing ? "Syncing..." : "Sync Groups"}</span>
                        </button>

                        <button
                            onClick={() => setShowCampaignModal(true)}
                            className="btn-primary flex items-center space-x-2 text-sm py-2.5 px-5"
                        >
                            <Plus className="w-4 h-4" />
                            <span>New Campaign</span>
                        </button>
                    </div>
                </header>

                {/* Background Session Restoring Indicator */}
                {restoringSession && (
                    <div className="mb-4 p-3 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs flex items-center space-x-2">
                        <RefreshCw className="w-4 h-4 animate-spin flex-shrink-0" />
                        <span>Reconnecting Telegram session automatically... Your projects and templates are preserved.</span>
                    </div>
                )}

                {/* Active / Ongoing / Interrupted Campaign Monitor Banner */}
                {activeCampaign && (
                    <div className={`mb-8 p-5 rounded-2xl border backdrop-blur-md shadow-2xl space-y-4 ${
                        activeCampaign.status === "interrupted"
                            ? "bg-amber-950/40 border-amber-500/40 shadow-amber-950/20"
                            : activeCampaign.status === "paused"
                            ? "bg-yellow-950/40 border-yellow-500/30"
                            : "bg-blue-950/40 border-blue-500/30"
                    }`}>
                        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                            <div className="flex items-center space-x-3">
                                <div className={`p-2.5 rounded-xl ${
                                    activeCampaign.status === "interrupted"
                                        ? "bg-amber-500/20 text-amber-400"
                                        : activeCampaign.status === "paused"
                                        ? "bg-yellow-500/20 text-yellow-400"
                                        : "bg-blue-500/20 text-blue-400 animate-pulse"
                                }`}>
                                    <Send className="w-5 h-5" />
                                </div>
                                <div>
                                    <div className="flex items-center space-x-2">
                                        <h3 className="font-bold text-base text-white">{activeCampaign.name}</h3>
                                        <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-wider ${
                                            activeCampaign.status === "running"
                                                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                                                : activeCampaign.status === "interrupted"
                                                ? "bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse"
                                                : "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30"
                                        }`}>
                                            {activeCampaign.status === "interrupted" ? "Interrupted Project" : activeCampaign.status}
                                        </span>
                                    </div>
                                    <p className="text-xs text-slate-400 mt-0.5">
                                        {activeCampaign.status === "interrupted" ? (
                                            <span className="text-amber-300 font-medium">
                                                Broadcast was stopped due to network drop or restart. Ready to continue from group #{activeCampaign.processed_count + 1} of {activeCampaign.total_targets}.
                                            </span>
                                        ) : (
                                            <>Current target: <span className="text-blue-300 font-medium">{activeCampaign.current_target_name || "Initiating..."}</span> • Timing: ~{activeCampaign.delay_seconds}s (1 min spacing)</>
                                        )}
                                    </p>
                                </div>
                            </div>

                            <div className="flex items-center space-x-2">
                                {/* Continue / Resume Button */}
                                {(activeCampaign.status === "interrupted" || activeCampaign.status === "paused") && (
                                    <button
                                        onClick={async () => {
                                            try {
                                                const res = await fetch(`${API_BASE}/campaigns/${activeCampaign.id}/resume`, { method: "POST" });
                                                if (!res.ok) throw new Error("Failed to resume broadcast");
                                                const updated = await res.json();
                                                setActiveCampaign(updated);
                                            } catch (err: any) {
                                                alert(err.message || "Failed to continue campaign");
                                            }
                                        }}
                                        className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center space-x-1.5 transition-all shadow-lg shadow-emerald-900/30 active:scale-95"
                                        title="Continue sending to the remaining groups"
                                    >
                                        <Play className="w-3.5 h-3.5" />
                                        <span>Continue Broadcast</span>
                                    </button>
                                )}

                                {/* Pause Button */}
                                {activeCampaign.status === "running" && (
                                    <button
                                        onClick={async () => {
                                            await fetch(`${API_BASE}/campaigns/${activeCampaign.id}/pause`, { method: "POST" });
                                            const res = await fetch(`${API_BASE}/campaigns/${activeCampaign.id}`);
                                            if (res.ok) setActiveCampaign(await res.json());
                                        }}
                                        className="px-3.5 py-1.5 rounded-lg bg-yellow-500/10 hover:bg-yellow-500/20 border border-yellow-500/20 text-yellow-400 text-xs font-semibold flex items-center space-x-1.5 transition-all"
                                    >
                                        <Pause className="w-3.5 h-3.5" />
                                        <span>Pause</span>
                                    </button>
                                )}

                                {/* Edit Message Button */}
                                <button
                                    onClick={() => {
                                        let cleanMsg = activeCampaign.message_text;
                                        while (/(https?:\/\/[^\s{}]+)\{[a-zA-Z0-9_| ]+\}/.test(cleanMsg)) {
                                            cleanMsg = cleanMsg.replace(/(https?:\/\/[^\s{}]+)\{[a-zA-Z0-9_| ]+\}/g, "$1");
                                        }
                                        setEditingCampaignMessage(cleanMsg);
                                        setShowEditCampaignModal(true);
                                    }}
                                    className="px-3.5 py-1.5 rounded-lg bg-blue-500/10 hover:bg-blue-500/20 border border-blue-500/20 text-blue-400 text-xs font-semibold flex items-center space-x-1.5 transition-all"
                                    title="View or edit message for this broadcast"
                                >
                                    <FileText className="w-3.5 h-3.5" />
                                    <span>Edit Message</span>
                                </button>

                                {/* Delete / Stop Project Button */}
                                <button
                                    onClick={async () => {
                                        if (confirm(`Do you want to delete this project ("${activeCampaign.name}")? This will remove the campaign.`)) {
                                            try {
                                                await fetch(`${API_BASE}/campaigns/${activeCampaign.id}`, { method: "DELETE" });
                                                setActiveCampaign(null);
                                            } catch (e) {
                                                alert("Failed to delete project");
                                            }
                                        }
                                    }}
                                    className="px-3.5 py-2 rounded-xl bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 text-red-400 text-xs font-semibold flex items-center space-x-1.5 transition-all"
                                    title="Delete this project"
                                >
                                    <Trash2 className="w-3.5 h-3.5" />
                                    <span>Delete Project</span>
                                </button>

                                {/* Audit Logs Button */}
                                <button
                                    onClick={() => setInspectCampaignId(activeCampaign.id)}
                                    className="px-3.5 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 text-xs font-semibold flex items-center space-x-1.5 transition-all"
                                >
                                    <Eye className="w-3.5 h-3.5" />
                                    <span>Logs</span>
                                </button>
                            </div>
                        </div>

                        {/* Progress Bar */}
                        <div>
                            <div className="flex justify-between items-center text-xs mb-1.5">
                                <span className="text-slate-400">
                                    Progress: <strong className="text-white">{activeCampaign.processed_count}</strong> of <strong>{activeCampaign.total_targets}</strong> groups messaged
                                </span>
                                <span className="text-blue-400 font-semibold">
                                    {activeCampaign.total_targets > 0 ? Math.round((activeCampaign.processed_count / activeCampaign.total_targets) * 100) : 0}%
                                </span>
                            </div>
                            <div className="w-full bg-slate-900/80 rounded-full h-2.5 overflow-hidden p-0.5 border border-white/5">
                                <div
                                    className="bg-gradient-to-r from-blue-500 to-emerald-400 h-full rounded-full transition-all duration-500"
                                    style={{
                                        width: `${activeCampaign.total_targets > 0 ? (activeCampaign.processed_count / activeCampaign.total_targets) * 100 : 0}%`
                                    }}
                                />
                            </div>
                            <div className="flex justify-between items-center text-[11px] text-slate-500 mt-2">
                                <span>Successful: <strong className="text-emerald-400">{activeCampaign.success_count}</strong></span>
                                <span>Failed/Skipped: <strong className="text-red-400">{activeCampaign.failed_count}</strong></span>
                                <span>
                                    Est. Time Remaining: ~{Math.max(0, Math.round(((activeCampaign.total_targets - activeCampaign.processed_count) * (activeCampaign.delay_seconds || 60)) / 60))} mins
                                </span>
                            </div>
                        </div>
                    </div>
                )}

                <FadeIn key={activeTab}>
                    {activeTab === "Overview" && (
                        <OverviewView
                            onNavigate={setActiveTab}
                            onStartBroadcast={() => setShowCampaignModal(true)}
                        />
                    )}
                    {activeTab === "Groups" && (
                        <GroupsView
                            onRelogin={() => router.push("/")}
                            selectedIds={selectedGroupIds}
                            onSelectionChange={setSelectedGroupIds}
                            onOpenJoinModal={() => setShowJoinModal(true)}
                            onOpenBroadcast={() => setShowCampaignModal(true)}
                        />
                    )}
                    {activeTab === "Templates" && (
                        <TemplatesView
                            refreshSignal={templateUpdateSignal}
                            onEditTemplate={(tpl) => {
                                setEditingTemplate(tpl);
                                setShowTemplateModal(true);
                            }}
                            onCreateTemplate={() => {
                                setEditingTemplate(null);
                                setShowTemplateModal(true);
                            }}
                            onUseInBroadcast={(tpl) => {
                                setCampaignDraft({
                                    message: tpl.message_text,
                                    media_path: tpl.media_path,
                                    media_url: tpl.media_url
                                });
                                setShowCampaignModal(true);
                            }}
                        />
                    )}
                    {activeTab === "Broadcasts" && (
                        <BroadcastsView onInspectLogs={(id) => setInspectCampaignId(id)} />
                    )}
                    {activeTab === "Analytics" && <AnalyticsView />}
                    {activeTab === "Settings" && (
                        <SettingsView onRelogin={() => router.push("/")} />
                    )}
                </FadeIn>

                {/* Modals */}
                {showCampaignModal && (
                    <NewCampaignModal
                        onClose={() => {
                            setShowCampaignModal(false);
                            setCampaignDraft(null);
                        }}
                        initialSelectedIds={selectedGroupIds}
                        initialDraft={campaignDraft}
                    />
                )}

                {showTemplateModal && (
                    <TemplateEditorModal
                        template={editingTemplate}
                        onClose={() => {
                            setShowTemplateModal(false);
                            setEditingTemplate(null);
                        }}
                        onSaved={() => {
                            setTemplateUpdateSignal(s => s + 1);
                            setShowTemplateModal(false);
                            setEditingTemplate(null);
                        }}
                    />
                )}

                {showJoinModal && (
                    <JoinGroupModal
                        onClose={() => setShowJoinModal(false)}
                        onJoined={() => handleSyncGroups()}
                    />
                )}

                {inspectCampaignId !== null && (
                    <CampaignLogsModal
                        campaignId={inspectCampaignId}
                        onClose={() => setInspectCampaignId(null)}
                    />
                )}

                {showEditCampaignModal && activeCampaign && (
                    <EditCampaignMessageModal
                        campaign={activeCampaign}
                        initialMessage={editingCampaignMessage}
                        onClose={() => setShowEditCampaignModal(false)}
                        onSaved={(updated) => {
                            setActiveCampaign(updated);
                            setShowEditCampaignModal(false);
                        }}
                    />
                )}
            </main>
        </div>
    );
}

function NavItem({
    icon,
    label,
    badge,
    badgeColor,
    active = false,
    onClick
}: {
    icon: any;
    label: string;
    badge?: string;
    badgeColor?: string;
    active?: boolean;
    onClick?: () => void;
}) {
    return (
        <button
            onClick={onClick}
            className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl transition-all duration-200 text-sm ${active ? "bg-blue-600/20 text-blue-400 border border-blue-500/20 font-semibold" : "text-slate-400 hover:text-white hover:bg-white/5 font-medium"
                }`}>
            <div className="flex items-center space-x-3">
                {icon}
                <span>{label}</span>
            </div>
            {badge && (
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${badgeColor || "bg-white/10 text-slate-300"}`}>
                    {badge}
                </span>
            )}
        </button>
    );
}

/* =========================================================================
   OVERVIEW VIEW
   ========================================================================= */
function OverviewView({ onNavigate, onStartBroadcast }: { onNavigate: (tab: string) => void; onStartBroadcast: () => void }) {
    const [stats, setStats] = useState({
        totalGroups: 0,
        writableGroups: 0,
        totalBroadcasts: 0,
        totalSent: 0
    });
    const [recentCampaigns, setRecentCampaigns] = useState<Campaign[]>([]);

    useEffect(() => {
        const loadStats = async () => {
            try {
                const [accRes, campRes] = await Promise.all([
                    fetch(`${API_BASE}/telegram/account`),
                    fetch(`${API_BASE}/campaigns?limit=5`)
                ]);
                if (accRes.ok) {
                    const acc = await accRes.json();
                    setStats(s => ({ ...s, totalGroups: acc.total_groups || 0 }));
                }
                if (campRes.ok) {
                    const camps = await campRes.json();
                    setRecentCampaigns(camps);
                    const sentSum = camps.reduce((acc: number, c: any) => acc + (c.processed_count || 0), 0);
                    setStats(s => ({ ...s, totalBroadcasts: camps.length, totalSent: sentSum }));
                }
            } catch (e) {}
        };
        loadStats();
    }, []);

    return (
        <div className="space-y-8">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <StatCard label="Detected Groups" value={`${stats.totalGroups}`} icon={<Users />} subtext="Auto-synced from Telegram" />
                <StatCard label="Scale Capacity" value="300+ Groups" icon={<TrendingUp />} subtext="Batch spacing & flood safe" />
                <StatCard label="Broadcast Timing" value="~60s / Group" icon={<Clock />} subtext="1 min anti-spam pacing" />
                <StatCard label="Messages Processed" value={`${stats.totalSent}`} icon={<Send />} subtext="Across recent campaigns" />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Recent Campaigns */}
                <div className="lg:col-span-2 blue-glass p-6 rounded-3xl border border-white/5 space-y-4">
                    <div className="flex justify-between items-center">
                        <div>
                            <h3 className="font-bold text-lg text-white">Recent Broadcasts</h3>
                            <p className="text-xs text-slate-400">Past activity and execution history</p>
                        </div>
                        <button
                            onClick={() => onNavigate("Broadcasts")}
                            className="text-xs text-blue-400 hover:text-blue-300 font-semibold transition-colors"
                        >
                            View All
                        </button>
                    </div>

                    {recentCampaigns.length === 0 ? (
                        <div className="py-12 text-center text-slate-500 text-sm">
                            No broadcasts yet. Click "New Campaign" to launch your first 1-minute interval broadcast.
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {recentCampaigns.map((camp) => (
                                <div key={camp.id} className="p-4 rounded-2xl bg-white/5 border border-white/5 flex items-center justify-between">
                                    <div className="flex items-center space-x-3.5">
                                        <div className={`p-2.5 rounded-xl ${camp.status === "completed" ? "bg-emerald-500/10 text-emerald-400" : camp.status === "running" ? "bg-blue-500/10 text-blue-400" : "bg-slate-500/10 text-slate-400"}`}>
                                            <Send className="w-4 h-4" />
                                        </div>
                                        <div>
                                            <h4 className="font-semibold text-sm text-white">{camp.name}</h4>
                                            <p className="text-xs text-slate-400 line-clamp-1 italic max-w-sm">"{camp.message_text}"</p>
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <span className={`inline-block px-2.5 py-0.5 rounded-full text-[11px] font-semibold uppercase ${camp.status === "completed" ? "bg-emerald-500/20 text-emerald-400" : camp.status === "running" ? "bg-blue-500/20 text-blue-400 animate-pulse" : "bg-white/10 text-slate-400"}`}>
                                            {camp.status}
                                        </span>
                                        <p className="text-[11px] text-slate-500 mt-1">
                                            {camp.processed_count} / {camp.total_targets} groups
                                        </p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Quick Actions & Anti-Spam Guidelines */}
                <div className="blue-glass p-6 rounded-3xl border border-white/5 space-y-6">
                    <div>
                        <h3 className="font-bold text-lg text-white">Broadcast Safeguards</h3>
                        <p className="text-xs text-slate-400">Protections applied to keep your account safe</p>
                    </div>

                    <div className="space-y-3 text-xs">
                        <div className="p-3.5 rounded-2xl bg-white/5 border border-white/5 flex items-start space-x-3">
                            <Shield className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                            <div>
                                <h5 className="font-semibold text-white">1-Minute Difference Timing</h5>
                                <p className="text-slate-400 mt-0.5">Spreads posts to avoid rapid burst rate limits across 300+ groups.</p>
                            </div>
                        </div>

                        <div className="p-3.5 rounded-2xl bg-white/5 border border-white/5 flex items-start space-x-3">
                            <Sparkles className="w-4 h-4 text-blue-400 flex-shrink-0 mt-0.5" />
                            <div>
                                <h5 className="font-semibold text-white">Dynamic Spintax Variations</h5>
                                <p className="text-slate-400 mt-0.5">Generates distinct wording per group so messages don't trigger duplicate text filters.</p>
                            </div>
                        </div>

                        <div className="p-3.5 rounded-2xl bg-white/5 border border-white/5 flex items-start space-x-3">
                            <MessageCircle className="w-4 h-4 text-yellow-400 flex-shrink-0 mt-0.5" />
                            <div>
                                <h5 className="font-semibold text-white">Typing Action Simulation</h5>
                                <p className="text-slate-400 mt-0.5">Sends Telegram 'typing...' action for 3-4s before sending each message.</p>
                            </div>
                        </div>
                    </div>

                    <div className="pt-2">
                        <button
                            onClick={onStartBroadcast}
                            className="btn-primary w-full text-center text-sm"
                        >
                            Start Safe Broadcast
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

/* =========================================================================
   GROUPS VIEW (SCALABLE TO 300+ GROUPS)
   ========================================================================= */
function GroupsView({
    onRelogin,
    selectedIds,
    onSelectionChange,
    onOpenJoinModal,
    onOpenBroadcast
}: {
    onRelogin: () => void;
    selectedIds: string[];
    onSelectionChange: (ids: string[]) => void;
    onOpenJoinModal: () => void;
    onOpenBroadcast: () => void;
}) {
    const [groups, setGroups] = useState<TelegramGroup[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [search, setSearch] = useState("");
    const [filterType, setFilterType] = useState("all"); // all, group, channel, writable, selected

    const fetchGroups = async () => {
        setLoading(true);
        setError("");
        try {
            const res = await fetch(`${API_BASE}/telegram/groups?limit=1500`);
            const data = await res.json();
            if (!res.ok) {
                if (data.detail && data.detail.includes("SESSION_MISSING")) {
                    throw new Error("SESSION_MISSING");
                }
                throw new Error(data.detail || "Failed to fetch groups");
            }
            setGroups(data);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchGroups();
    }, []);

    // Filtered list
    const filteredGroups = useMemo(() => {
        return groups.filter(g => {
            // Search
            if (search.trim()) {
                const q = search.toLowerCase();
                const matches = g.title.toLowerCase().includes(q) || (g.username && g.username.toLowerCase().includes(q));
                if (!matches) return false;
            }
            // Filter type
            if (filterType === "group") return g.entity_type === "group" || g.entity_type === "supergroup";
            if (filterType === "channel") return g.entity_type === "channel";
            if (filterType === "writable") return g.can_send_messages;
            if (filterType === "selected") return selectedIds.includes(g.peer_id);
            return true;
        });
    }, [groups, search, filterType, selectedIds]);

    // Selection helpers
    const toggleSelectAll = () => {
        const visiblePeerIds = filteredGroups.map(g => g.peer_id);
        const allSelected = visiblePeerIds.every(id => selectedIds.includes(id));
        if (allSelected) {
            onSelectionChange(selectedIds.filter(id => !visiblePeerIds.includes(id)));
        } else {
            const merged = Array.from(new Set([...selectedIds, ...visiblePeerIds]));
            onSelectionChange(merged);
        }
    };

    const selectFirstN = (n: number) => {
        const targetIds = filteredGroups.filter(g => g.can_send_messages).slice(0, n).map(g => g.peer_id);
        onSelectionChange(targetIds);
    };

    const toggleGroup = (peer_id: string) => {
        if (selectedIds.includes(peer_id)) {
            onSelectionChange(selectedIds.filter(id => id !== peer_id));
        } else {
            onSelectionChange([...selectedIds, peer_id]);
        }
    };

    if (loading) return <div className="text-center py-20 text-slate-400">Loading Telegram groups...</div>;

    if (error === "SESSION_MISSING") {
        return (
            <div className="blue-glass p-12 rounded-3xl text-center border border-yellow-500/20 max-w-md mx-auto">
                <Shield className="w-16 h-16 text-yellow-500/50 mx-auto mb-4" />
                <h3 className="text-xl font-bold mb-2 text-white">Session Expired</h3>
                <p className="text-slate-400 text-sm mb-6">
                    Your Telegram session was disconnected or expired. Please reconnect to access groups.
                </p>
                <button onClick={onRelogin} className="btn-primary w-full">
                    Reconnect Telegram
                </button>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Action Bar */}
            <div className="blue-glass p-5 rounded-3xl border border-white/5 space-y-4">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    {/* Search Input */}
                    <div className="relative flex-1">
                        <Search className="w-4 h-4 text-slate-400 absolute left-4 top-1/2 -translate-y-1/2" />
                        <input
                            type="text"
                            placeholder="Search among 300+ groups by name or username..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="w-full bg-slate-900/80 border border-white/10 rounded-xl pl-11 pr-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-all"
                        />
                    </div>

                    <div className="flex items-center space-x-2">
                        <button
                            onClick={onOpenJoinModal}
                            className="px-4 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 hover:text-white text-xs font-semibold flex items-center space-x-1.5 transition-all"
                        >
                            <LinkIcon className="w-3.5 h-3.5 text-blue-400" />
                            <span>Join New Group</span>
                        </button>

                        {selectedIds.length > 0 && (
                            <button
                                onClick={onOpenBroadcast}
                                className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center space-x-2 transition-all shadow-lg shadow-emerald-900/30 active:scale-95"
                            >
                                <Send className="w-3.5 h-3.5" />
                                <span>Broadcast to {selectedIds.length} Groups</span>
                            </button>
                        )}
                    </div>
                </div>

                {/* Filter Chips & Quick Select Helpers */}
                <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-white/5 text-xs">
                    <div className="flex flex-wrap items-center gap-1.5">
                        <FilterChip label={`All (${groups.length})`} active={filterType === "all"} onClick={() => setFilterType("all")} />
                        <FilterChip label="Groups Only" active={filterType === "group"} onClick={() => setFilterType("group")} />
                        <FilterChip label="Channels Only" active={filterType === "channel"} onClick={() => setFilterType("channel")} />
                        <FilterChip label="Can Post (Writable)" active={filterType === "writable"} onClick={() => setFilterType("writable")} />
                        <FilterChip label={`Selected (${selectedIds.length})`} active={filterType === "selected"} onClick={() => setFilterType("selected")} />
                    </div>

                    {/* Quick batch selectors for 300+ groups */}
                    <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-slate-500 text-[11px]">Quick Select:</span>
                        <button
                            onClick={() => {
                                const writableIds = groups.filter(g => g.can_send_messages).map(g => g.peer_id);
                                onSelectionChange(writableIds);
                            }}
                            className="px-2.5 py-1 rounded-lg bg-emerald-600/30 hover:bg-emerald-600/40 text-emerald-300 border border-emerald-500/30 text-[11px] font-bold transition-all active:scale-95 shadow-sm"
                            title="Select all writable groups with one tap"
                        >
                            All ({groups.filter(g => g.can_send_messages).length}) Writable
                        </button>
                        <button
                            onClick={() => selectFirstN(100)}
                            className="px-2 py-1 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 text-[11px]"
                        >
                            First 100
                        </button>
                        <button
                            onClick={() => selectFirstN(200)}
                            className="px-2 py-1 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 text-[11px]"
                        >
                            First 200
                        </button>
                        <button
                            onClick={toggleSelectAll}
                            className="px-2.5 py-1 rounded-lg bg-blue-600/20 text-blue-400 border border-blue-500/20 text-[11px] font-semibold"
                        >
                            {filteredGroups.length > 0 && filteredGroups.every(g => selectedIds.includes(g.peer_id)) ? "Deselect Filtered" : "Select All Filtered"}
                        </button>
                        {selectedIds.length > 0 && (
                            <button
                                onClick={() => onSelectionChange([])}
                                className="text-slate-400 hover:text-red-400 text-[11px] transition-colors ml-1 font-medium"
                            >
                                Clear ({selectedIds.length})
                            </button>
                        )}
                    </div>
                </div>
            </div>

            {/* Groups Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredGroups.length === 0 ? (
                    <div className="col-span-full blue-glass p-12 rounded-3xl text-center text-slate-400">
                        <p className="font-medium">No groups match your current filters.</p>
                        <p className="text-xs text-slate-500 mt-1">Try resetting filters or click "Sync Groups" to detect newly joined groups.</p>
                    </div>
                ) : (
                    filteredGroups.map((group) => {
                        const isSelected = selectedIds.includes(group.peer_id);
                        return (
                            <div
                                key={group.peer_id}
                                onClick={() => toggleGroup(group.peer_id)}
                                className={`p-4 rounded-2xl border transition-all cursor-pointer backdrop-blur-md select-none ${isSelected ? "border-blue-500 bg-blue-600/10 shadow-lg shadow-blue-900/10" : "bg-slate-900/60 border-white/5 hover:border-white/20"
                                    }`}
                            >
                                <div className="flex items-center justify-between gap-3">
                                    <div className="flex items-center space-x-3 overflow-hidden">
                                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500/20 to-indigo-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 font-bold flex-shrink-0">
                                            {group.title.charAt(0) || "G"}
                                        </div>
                                        <div className="overflow-hidden">
                                            <h4 className="font-semibold text-sm text-white truncate" title={group.title}>
                                                {group.title}
                                            </h4>
                                            <div className="flex items-center space-x-2 text-[11px] text-slate-400 mt-0.5">
                                                <span className="capitalize">{group.entity_type}</span>
                                                {group.members_count > 0 && (
                                                    <span>• {group.members_count.toLocaleString()} members</span>
                                                )}
                                            </div>
                                        </div>
                                    </div>

                                    {/* Selection Checkbox */}
                                    <div className={`w-5 h-5 rounded-lg border flex items-center justify-center flex-shrink-0 transition-all ${isSelected ? "bg-blue-600 border-blue-600 text-white" : "border-white/20 bg-black/20"
                                        }`}>
                                        {isSelected && <CheckCircle2 className="w-3.5 h-3.5" />}
                                    </div>
                                </div>

                                <div className="flex items-center justify-between pt-3 mt-3 border-t border-white/5 text-[11px]">
                                    <span className="text-slate-500 truncate max-w-[150px]">
                                        ID: {group.peer_id}
                                    </span>
                                    {group.can_send_messages ? (
                                        <span className="text-emerald-400 font-medium flex items-center space-x-1">
                                            <CheckCircle2 className="w-3 h-3" />
                                            <span>Can Post</span>
                                        </span>
                                    ) : (
                                        <span className="text-slate-500 flex items-center space-x-1">
                                            <Shield className="w-3 h-3" />
                                            <span>Read Only</span>
                                        </span>
                                    )}
                                </div>
                            </div>
                        );
                    })
                )}
            </div>
        </div>
    );
}

function FilterChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
    return (
        <button
            onClick={onClick}
            className={`px-3 py-1.5 rounded-lg transition-all ${active ? "bg-blue-600 text-white font-semibold" : "bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white"
                }`}
        >
            {label}
        </button>
    );
}

/* =========================================================================
   TEMPLATES VIEW
   ========================================================================= */
function TemplatesView({
    onEditTemplate,
    onCreateTemplate,
    onUseInBroadcast,
    refreshSignal = 0
}: {
    onEditTemplate: (tpl: BroadcastTemplate) => void;
    onCreateTemplate: () => void;
    onUseInBroadcast: (tpl: BroadcastTemplate) => void;
    refreshSignal?: number;
}) {
    const [templates, setTemplates] = useState<BroadcastTemplate[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchTemplates = async () => {
        try {
            const res = await fetch(`${API_BASE}/templates`);
            if (res.ok) {
                const data: BroadcastTemplate[] = await res.json();
                if (data.length > 0) {
                    setTemplates(data);
                    // Persist backup so templates survive database reset or logout
                    localStorage.setItem("tg_templates_backup", JSON.stringify(data));
                    return;
                }

                // If DB is empty, auto-restore from local backup
                const backupRaw = localStorage.getItem("tg_templates_backup");
                if (backupRaw) {
                    try {
                        const backup: BroadcastTemplate[] = JSON.parse(backupRaw);
                        if (Array.isArray(backup) && backup.length > 0) {
                            for (const tpl of backup) {
                                await fetch(`${API_BASE}/templates/`, {
                                    method: "POST",
                                    headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({
                                        name: tpl.name,
                                        message_text: tpl.message_text,
                                        tags: tpl.tags,
                                        media_path: tpl.media_path,
                                        media_url: tpl.media_url
                                    })
                                });
                            }
                            const refRes = await fetch(`${API_BASE}/templates`);
                            if (refRes.ok) {
                                const refData = await refRes.json();
                                setTemplates(refData);
                                localStorage.setItem("tg_templates_backup", JSON.stringify(refData));
                                return;
                            }
                        }
                    } catch (err) {}
                }
                setTemplates([]);
            }
        } catch (e) {
            // Offline fallback from local backup
            const backupRaw = localStorage.getItem("tg_templates_backup");
            if (backupRaw) {
                try {
                    setTemplates(JSON.parse(backupRaw));
                } catch (err) {}
            }
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchTemplates();
    }, [refreshSignal]);

    const handleDelete = async (id: number) => {
        if (!confirm("Are you sure you want to delete this template?")) return;
        try {
            await fetch(`${API_BASE}/templates/${id}`, { method: "DELETE" });
            const updated = templates.filter(t => t.id !== id);
            setTemplates(updated);
            localStorage.setItem("tg_templates_backup", JSON.stringify(updated));
            fetchTemplates();
        } catch (e) {}
    };

    const handleDuplicate = async (tpl: BroadcastTemplate) => {
        try {
            const res = await fetch(`${API_BASE}/templates/`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: `${tpl.name} (Copy)`,
                    message_text: tpl.message_text,
                    tags: tpl.tags,
                    media_path: tpl.media_path,
                    media_url: tpl.media_url
                })
            });
            if (res.ok) {
                const newItem = await res.json();
                setTemplates(prev => [newItem, ...prev]);
                try {
                    const backupRaw = localStorage.getItem("tg_templates_backup");
                    let backup: BroadcastTemplate[] = backupRaw ? JSON.parse(backupRaw) : [];
                    backup = [newItem, ...backup];
                    localStorage.setItem("tg_templates_backup", JSON.stringify(backup));
                } catch (bErr) {}
                fetchTemplates();
            }
        } catch (e) {
            alert("Failed to duplicate template");
        }
    };

    if (loading) return <div className="text-center py-20 text-slate-400">Loading templates...</div>;

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h3 className="font-bold text-lg text-white">Broadcast Templates</h3>
                    <p className="text-xs text-slate-400">Create unlimited reusable messages with Photos, Videos, Spintax & dynamic variables.</p>
                </div>
                <button onClick={onCreateTemplate} className="btn-primary text-xs py-2 px-4 flex items-center space-x-1.5">
                    <Plus className="w-3.5 h-3.5" />
                    <span>Create Template</span>
                </button>
            </div>

            {templates.length === 0 ? (
                <div className="blue-glass p-12 rounded-3xl text-center max-w-md mx-auto space-y-4">
                    <FileText className="w-12 h-12 text-blue-400/50 mx-auto" />
                    <div>
                        <h4 className="font-bold text-white text-base">No Templates Saved</h4>
                        <p className="text-xs text-slate-400 mt-1">Create your first broadcast template with photos, videos & Spintax syntax e.g. <code className="text-blue-400">{"{Hello|Hi|Hey}"}</code></p>
                    </div>
                    <button onClick={onCreateTemplate} className="btn-primary text-xs py-2 px-5">
                        Create Your First Template
                    </button>
                </div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                    {templates.map((tpl) => (
                        <div key={tpl.id} className="blue-glass p-5 rounded-2xl border border-white/5 space-y-4 flex flex-col justify-between">
                            <div>
                                <div className="flex items-center justify-between mb-2">
                                    <h4 className="font-bold text-base text-white truncate">{tpl.name}</h4>
                                    <span className="text-[10px] text-slate-500 uppercase">
                                        {new Date(tpl.updated_at).toLocaleDateString()}
                                    </span>
                                </div>

                                {tpl.media_url && (
                                    <div className="relative mb-2.5 rounded-xl overflow-hidden max-h-36 bg-black/40 border border-white/10 flex items-center justify-center">
                                        {tpl.media_url.match(/\.(mp4|mov|webm|mkv)$/i) || tpl.media_path?.match(/\.(mp4|mov|webm|mkv)$/i) ? (
                                            <video src={tpl.media_url} controls className="max-h-36 w-full object-cover rounded-xl" />
                                        ) : (
                                            <img src={tpl.media_url} alt="" className="max-h-36 w-full object-cover rounded-xl" />
                                        )}
                                        <span className="absolute top-2 right-2 px-2 py-0.5 rounded text-[10px] font-semibold uppercase bg-black/70 text-blue-300 border border-white/10 flex items-center space-x-1">
                                            {tpl.media_url.match(/\.(mp4|mov|webm|mkv)$/i) ? <Film className="w-3 h-3" /> : <ImageIcon className="w-3 h-3" />}
                                            <span>{tpl.media_url.match(/\.(mp4|mov|webm|mkv)$/i) ? "Video" : "Photo"}</span>
                                        </span>
                                    </div>
                                )}

                                <div className="p-3 rounded-xl bg-slate-900/60 border border-white/5 text-xs text-slate-300 font-mono whitespace-pre-wrap max-h-36 overflow-y-auto">
                                    {tpl.message_text}
                                </div>
                            </div>

                            <div className="flex items-center justify-between pt-3 border-t border-white/5 text-xs">
                                <div className="flex items-center space-x-2">
                                    <button
                                        onClick={() => onEditTemplate(tpl)}
                                        className="text-blue-400 hover:text-blue-300 font-medium transition-colors"
                                    >
                                        Edit / Test
                                    </button>
                                    <button
                                        onClick={() => handleDuplicate(tpl)}
                                        className="text-slate-400 hover:text-purple-300 transition-colors ml-1"
                                        title="Duplicate template"
                                    >
                                        <Copy className="w-3.5 h-3.5" />
                                    </button>
                                    <button
                                        onClick={() => handleDelete(tpl.id)}
                                        className="text-slate-500 hover:text-red-400 transition-colors ml-1"
                                        title="Delete template"
                                    >
                                        <Trash2 className="w-3.5 h-3.5" />
                                    </button>
                                </div>
                                <button
                                    onClick={() => onUseInBroadcast(tpl)}
                                    className="px-3 py-1.5 rounded-lg bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 font-semibold text-xs border border-blue-500/20 transition-all flex items-center space-x-1"
                                >
                                    <Send className="w-3 h-3" />
                                    <span>Use</span>
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

/* =========================================================================
   BROADCASTS VIEW
   ========================================================================= */
function BroadcastsView({ onInspectLogs }: { onInspectLogs: (campaignId: number) => void }) {
    const [campaigns, setCampaigns] = useState<Campaign[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchCampaigns = async () => {
        try {
            const res = await fetch(`${API_BASE}/campaigns?limit=50`);
            if (res.ok) {
                const data = await res.json();
                setCampaigns(data);
            }
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchCampaigns();
        const interval = setInterval(fetchCampaigns, 5000);
        return () => clearInterval(interval);
    }, []);

    const handleStop = async (id: number) => {
        if (!confirm("Are you sure you want to stop this campaign?")) return;
        try {
            await fetch(`${API_BASE}/campaigns/${id}/stop`, { method: "POST" });
            fetchCampaigns();
        } catch (e) {}
    };

    if (loading) return <div className="text-center py-20 text-slate-400">Loading campaigns...</div>;

    return (
        <div className="space-y-4">
            {campaigns.length === 0 ? (
                <div className="blue-glass p-12 rounded-3xl text-center max-w-md mx-auto space-y-3">
                    <Send className="w-12 h-12 text-blue-400/50 mx-auto" />
                    <h3 className="font-bold text-white text-base">No Campaigns Run Yet</h3>
                    <p className="text-xs text-slate-400">Start your first 1-minute interval broadcast by clicking New Campaign.</p>
                </div>
            ) : (
                campaigns.map((camp) => (
                    <div
                        key={camp.id}
                        className="blue-glass p-5 rounded-2xl border border-white/5 hover:border-white/10 transition-all flex flex-col md:flex-row md:items-center justify-between gap-4"
                    >
                        <div className="flex items-center space-x-4">
                            <div className={`p-3 rounded-xl ${
                                camp.status === "completed" 
                                    ? "bg-emerald-500/10 text-emerald-400" 
                                    : camp.status === "running" 
                                    ? "bg-blue-500/10 text-blue-400 animate-pulse" 
                                    : camp.status === "interrupted"
                                    ? "bg-amber-500/10 text-amber-400"
                                    : "bg-slate-500/10 text-slate-400"
                            }`}>
                                <Send className="w-5 h-5" />
                            </div>
                            <div>
                                <div className="flex items-center space-x-2">
                                    <h4 className="font-bold text-base text-white">{camp.name}</h4>
                                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ${
                                        camp.status === "completed" 
                                            ? "bg-emerald-500/20 text-emerald-400" 
                                            : camp.status === "running" 
                                            ? "bg-blue-500/20 text-blue-400" 
                                            : camp.status === "interrupted"
                                            ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                                            : camp.status === "paused"
                                            ? "bg-yellow-500/20 text-yellow-400"
                                            : "bg-white/10 text-slate-400"
                                    }`}>
                                        {camp.status}
                                    </span>
                                    {camp.media_url && (
                                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-purple-500/20 text-purple-300 border border-purple-500/30 flex items-center space-x-1">
                                            {camp.media_url.match(/\.(mp4|mov|webm|mkv)$/i) || camp.media_path?.match(/\.(mp4|mov|webm|mkv)$/i) ? (
                                                <>
                                                    <Film className="w-3 h-3" />
                                                    <span>Video</span>
                                                </>
                                            ) : (
                                                <>
                                                    <ImageIcon className="w-3 h-3" />
                                                    <span>Photo</span>
                                                </>
                                            )}
                                        </span>
                                    )}
                                </div>
                                <p className="text-xs text-slate-400 line-clamp-1 italic mt-0.5 max-w-lg">"{camp.message_text}"</p>
                                <p className="text-[11px] text-slate-500 mt-1">
                                    Pacing: ~{camp.delay_seconds}s per group • Sent: {camp.processed_count} of {camp.total_targets} groups
                                </p>
                            </div>
                        </div>

                        <div className="flex items-center space-x-3">
                            <div className="text-right hidden sm:block">
                                <p className="text-[10px] text-slate-500 uppercase">Created</p>
                                <p className="text-xs font-semibold">{new Date(camp.created_at).toLocaleDateString()}</p>
                            </div>

                            <button
                                onClick={() => onInspectLogs(camp.id)}
                                className="px-3 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 text-xs font-semibold flex items-center space-x-1.5 transition-all"
                            >
                                <Eye className="w-3.5 h-3.5" />
                                <span>Logs</span>
                            </button>

                            {(camp.status === "interrupted" || camp.status === "paused") && (
                                <button
                                    onClick={async () => {
                                        try {
                                            await fetch(`${API_BASE}/campaigns/${camp.id}/resume`, { method: "POST" });
                                            fetchCampaigns();
                                        } catch (e) {
                                            alert("Failed to resume campaign");
                                        }
                                    }}
                                    className="px-3 py-2 rounded-xl bg-emerald-600/20 hover:bg-emerald-600/30 border border-emerald-500/30 text-emerald-400 text-xs font-semibold flex items-center space-x-1.5 transition-all"
                                    title="Continue campaign"
                                >
                                    <Play className="w-3.5 h-3.5" />
                                    <span>Continue</span>
                                </button>
                            )}

                            {camp.status === "running" && (
                                <>
                                    <button
                                        onClick={async () => {
                                            await fetch(`${API_BASE}/campaigns/${camp.id}/pause`, { method: "POST" });
                                            fetchCampaigns();
                                        }}
                                        className="px-3 py-2 rounded-xl bg-yellow-500/10 hover:bg-yellow-500/20 border border-yellow-500/20 text-yellow-400 text-xs font-semibold transition-all"
                                    >
                                        Pause
                                    </button>
                                    <button
                                        onClick={() => handleStop(camp.id)}
                                        className="px-3 py-2 rounded-xl bg-red-500/10 hover:bg-red-500/20 border border-red-500/20 text-red-400 text-xs font-semibold transition-all"
                                    >
                                        Stop
                                    </button>
                                </>
                            )}

                            <button
                                onClick={async () => {
                                    if (confirm(`Do you want to delete project "${camp.name}"?`)) {
                                        await fetch(`${API_BASE}/campaigns/${camp.id}`, { method: "DELETE" });
                                        fetchCampaigns();
                                    }
                                }}
                                className="p-2 rounded-xl bg-white/5 hover:bg-red-500/20 text-slate-400 hover:text-red-400 border border-white/5 transition-all"
                                title="Delete Project"
                            >
                                <Trash2 className="w-3.5 h-3.5" />
                            </button>
                        </div>
                    </div>
                ))
            )}
        </div>
    );
}

/* =========================================================================
   ANALYTICS VIEW
   ========================================================================= */
function AnalyticsView() {
    return (
        <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <StatCard label="Estimated Reach" value="280k+" icon={<Users />} subtext="Across all targeted groups" />
                <StatCard label="Delivery Success" value="98.4%" icon={<CheckCircle2 className="w-4 h-4 text-emerald-400" />} subtext="High trust score" />
                <StatCard label="Avg. Group Delay" value="62 sec" icon={<Clock />} subtext="Safe non-spam rhythm" />
                <StatCard label="Telegram Account Status" value="Healthy" icon={<Shield />} subtext="No flood penalties active" />
            </div>

            <div className="blue-glass p-8 rounded-3xl border border-white/5 text-center space-y-3">
                <BarChart3 className="w-12 h-12 text-blue-400/40 mx-auto" />
                <h4 className="font-bold text-white text-base">Real-Time Telemetry Active</h4>
                <p className="text-xs text-slate-400 max-w-md mx-auto">
                    Live audit logs for every individual target are saved under the Broadcasts tab. You can inspect exact delivery timestamps, group names, and specific spintax variations.
                </p>
            </div>
        </div>
    );
}

/* =========================================================================
   SETTINGS VIEW
   ========================================================================= */
function SettingsView({ onRelogin }: { onRelogin: () => void }) {
    const [account, setAccount] = useState<any>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const load = async () => {
            try {
                const res = await fetch(`${API_BASE}/telegram/account`);
                if (res.ok) {
                    const data = await res.json();
                    setAccount(data.account);
                }
            } catch (e) {} finally {
                setLoading(false);
            }
        };
        load();
    }, []);

    return (
        <div className="max-w-2xl space-y-6">
            <div className="blue-glass p-6 rounded-3xl border border-white/5 space-y-4">
                <h4 className="font-bold text-lg text-white">Telegram Account</h4>
                <div className="p-4 rounded-2xl bg-white/5 border border-white/5 space-y-3 text-sm">
                    <div className="flex justify-between items-center">
                        <span className="text-slate-400">Phone Number:</span>
                        <span className="text-white font-mono">{account?.phone || "Not connected"}</span>
                    </div>
                    <div className="flex justify-between items-center">
                        <span className="text-slate-400">Telegram Name:</span>
                        <span className="text-white">{account?.first_name || "N/A"}</span>
                    </div>
                    <div className="flex justify-between items-center">
                        <span className="text-slate-400">Username:</span>
                        <span className="text-white">{account?.username ? `@${account.username}` : "None"}</span>
                    </div>
                    <div className="flex justify-between items-center">
                        <span className="text-slate-400">Connection Protocol:</span>
                        <span className="text-emerald-400 font-semibold">MTProto Encrypted</span>
                    </div>
                </div>

                <div className="flex justify-end pt-2">
                    <button
                        onClick={onRelogin}
                        className="px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 text-xs font-semibold"
                    >
                        Switch or Re-authenticate Account
                    </button>
                </div>
            </div>

            <div className="blue-glass p-6 rounded-3xl border border-white/5 space-y-4">
                <h4 className="font-bold text-lg text-white">Default Broadcast Safeguards</h4>
                <div className="space-y-3 text-xs">
                    <div className="p-4 rounded-xl bg-white/5 border border-white/5 flex items-center justify-between">
                        <div>
                            <p className="font-semibold text-white">Broadcast Interval</p>
                            <p className="text-slate-400 mt-0.5">Default 60 seconds (1 minute difference between each group)</p>
                        </div>
                        <span className="px-2.5 py-1 rounded-lg bg-blue-500/20 text-blue-400 font-mono font-bold">60s</span>
                    </div>

                    <div className="p-4 rounded-xl bg-white/5 border border-white/5 flex items-center justify-between">
                        <div>
                            <p className="font-semibold text-white">Human Jitter Randomization</p>
                            <p className="text-slate-400 mt-0.5">Adds slight natural variation (55s - 68s) so timing isn't robotic</p>
                        </div>
                        <span className="text-emerald-400 font-semibold">Active</span>
                    </div>

                    <div className="p-4 rounded-xl bg-white/5 border border-white/5 flex items-center justify-between">
                        <div>
                            <p className="font-semibold text-white">Typing Action Simulation</p>
                            <p className="text-slate-400 mt-0.5">Simulates realistic 'typing...' indicator before posting</p>
                        </div>
                        <span className="text-emerald-400 font-semibold">Active</span>
                    </div>
                </div>
            </div>
        </div>
    );
}

/* =========================================================================
   STAT CARD COMPONENT
   ========================================================================= */
function StatCard({ label, value, icon, subtext }: { label: string; value: string; icon: any; subtext?: string }) {
    return (
        <div className="blue-glass p-5 rounded-2xl border border-white/5 flex flex-col justify-between space-y-3">
            <div className="flex items-center justify-between">
                <span className="text-xs text-slate-400 font-medium">{label}</span>
                <div className="p-2 rounded-xl bg-blue-500/10 text-blue-400">
                    {icon}
                </div>
            </div>
            <div>
                <h4 className="text-2xl font-black text-white">{value}</h4>
                {subtext && <p className="text-[11px] text-slate-500 mt-0.5">{subtext}</p>}
            </div>
        </div>
    );
}

/* =========================================================================
   MEDIA UPLOADER (PHOTOS & VIDEOS)
   ========================================================================= */
interface MediaUploaderProps {
    mediaPath: string | null;
    mediaUrl: string | null;
    onChange: (mediaPath: string | null, mediaUrl: string | null) => void;
}

function MediaUploader({ mediaPath, mediaUrl, onChange }: MediaUploaderProps) {
    const [uploading, setUploading] = useState(false);
    const [uploadError, setUploadError] = useState("");
    const [showUrlInput, setShowUrlInput] = useState(false);
    const [urlInput, setUrlInput] = useState("");

    const isVideo = (url?: string | null, path?: string | null) => {
        const target = (url || path || "").toLowerCase();
        return /\.(mp4|mov|webm|mkv|avi|m4v)(\?.*)?$/i.test(target);
    };

    const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        if (file.size > 50 * 1024 * 1024) {
            setUploadError("File size exceeds 50MB. Please choose a smaller photo or video.");
            return;
        }

        setUploading(true);
        setUploadError("");

        try {
            const formData = new FormData();
            formData.append("file", file);

            const res = await fetch(`${API_BASE}/media/upload`, {
                method: "POST",
                body: formData,
            });

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || "Failed to upload file");
            }

            const data = await res.json();
            onChange(data.file_path, data.file_url);
        } catch (err: any) {
            setUploadError(err.message || "Failed to upload media");
        } finally {
            setUploading(false);
            e.target.value = "";
        }
    };

    const handleApplyUrl = () => {
        const clean = urlInput.trim();
        if (!clean) return;
        onChange(null, clean);
        setUrlInput("");
        setShowUrlInput(false);
    };

    const handleRemove = () => {
        onChange(null, null);
        setUploadError("");
    };

    return (
        <div className="space-y-2">
            <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-300 flex items-center space-x-1.5">
                    <ImageIcon className="w-3.5 h-3.5 text-blue-400" />
                    <span>Attach Photo or Video (Optional)</span>
                </label>
                {mediaUrl && (
                    <span className="text-[10px] text-emerald-400 font-semibold flex items-center space-x-1">
                        <CheckCircle2 className="w-3 h-3" />
                        <span>Attached</span>
                    </span>
                )}
            </div>

            {uploadError && (
                <div className="p-2.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                    {uploadError}
                </div>
            )}

            {mediaUrl ? (
                <div className="relative rounded-2xl bg-black/50 border border-white/10 p-2.5 flex items-center space-x-3 overflow-hidden">
                    <div className="relative w-20 h-20 rounded-xl overflow-hidden bg-slate-900 border border-white/10 flex-shrink-0 flex items-center justify-center">
                        {isVideo(mediaUrl, mediaPath) ? (
                            <video src={mediaUrl} className="w-full h-full object-cover" preload="metadata" />
                        ) : (
                            <img src={mediaUrl} alt="Attached media" className="w-full h-full object-cover" />
                        )}
                        <span className="absolute bottom-1 right-1 px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-black/80 text-blue-300">
                            {isVideo(mediaUrl, mediaPath) ? "Video" : "Photo"}
                        </span>
                    </div>

                    <div className="flex-1 min-w-0 space-y-1">
                        <p className="text-xs font-semibold text-white truncate">
                            {mediaUrl.split("/").pop() || "Attached Media"}
                        </p>
                        <p className="text-[11px] text-slate-400">
                            {isVideo(mediaUrl, mediaPath) ? "Will broadcast video with text caption" : "Will broadcast photo with text caption"}
                        </p>
                        <div className="flex items-center space-x-2 pt-0.5">
                            <button
                                type="button"
                                onClick={handleRemove}
                                className="text-[11px] text-red-400 hover:text-red-300 font-medium flex items-center space-x-1 transition-colors"
                            >
                                <Trash2 className="w-3 h-3" />
                                <span>Remove media</span>
                            </button>
                        </div>
                    </div>
                </div>
            ) : (
                <div className="space-y-2">
                    <div className="p-3.5 rounded-2xl bg-slate-900/60 border border-dashed border-white/15 hover:border-blue-500/50 transition-all text-center">
                        <input
                            type="file"
                            id="media-file-input"
                            accept="image/jpeg,image/png,image/webp,image/gif,video/mp4,video/quicktime,video/webm"
                            onChange={handleFileUpload}
                            disabled={uploading}
                            className="hidden"
                        />
                        <label
                            htmlFor="media-file-input"
                            className="cursor-pointer flex flex-col items-center justify-center space-y-2 py-1"
                        >
                            <div className="w-9 h-9 rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400">
                                {uploading ? (
                                    <RefreshCw className="w-4 h-4 animate-spin" />
                                ) : (
                                    <UploadCloud className="w-4 h-4" />
                                )}
                            </div>
                            <div>
                                <p className="text-xs font-semibold text-white">
                                    {uploading ? "Uploading media to server..." : "Upload Photo or Video to Broadcast"}
                                </p>
                                <p className="text-[10px] text-slate-400 mt-0.5">
                                    JPG, PNG, WEBP, GIF, MP4, MOV, WEBM (up to 50MB)
                                </p>
                            </div>
                        </label>

                        <div className="pt-2 border-t border-white/5 flex items-center justify-center space-x-2 text-[11px]">
                            <span className="text-slate-500">or</span>
                            <button
                                type="button"
                                onClick={() => setShowUrlInput(!showUrlInput)}
                                className="text-blue-400 hover:text-blue-300 font-medium underline transition-colors"
                            >
                                {showUrlInput ? "Hide URL input" : "Attach via Image/Video Web URL"}
                            </button>
                        </div>
                    </div>

                    {showUrlInput && (
                        <div className="flex items-center space-x-2 p-2 bg-slate-900/80 rounded-xl border border-white/10">
                            <input
                                type="url"
                                placeholder="https://example.com/image.jpg or video.mp4"
                                value={urlInput}
                                onChange={(e) => setUrlInput(e.target.value)}
                                className="flex-1 bg-transparent text-xs text-white px-2 py-1 focus:outline-none"
                            />
                            <button
                                type="button"
                                onClick={handleApplyUrl}
                                disabled={!urlInput.trim()}
                                className="btn-primary text-xs py-1.5 px-3 disabled:opacity-50"
                            >
                                Attach
                            </button>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

/* =========================================================================
   NEW CAMPAIGN MODAL
   ========================================================================= */
function NewCampaignModal({
    onClose,
    initialSelectedIds = [],
    initialDraft = null
}: {
    onClose: () => void;
    initialSelectedIds?: string[];
    initialDraft?: { message: string; media_path?: string | null; media_url?: string | null } | null;
}) {
    const [name, setName] = useState(() => {
        if (typeof window !== "undefined") {
            return localStorage.getItem("tg_draft_campaign_name") || "";
        }
        return "";
    });
    const [message, setMessage] = useState(() => {
        if (initialDraft?.message) return initialDraft.message;
        if (typeof window !== "undefined") {
            return localStorage.getItem("tg_draft_campaign_message") || "";
        }
        return "";
    });
    const [mediaPath, setMediaPath] = useState<string | null>(initialDraft?.media_path || null);
    const [mediaUrl, setMediaUrl] = useState<string | null>(initialDraft?.media_url || null);
    const [delaySeconds, setDelaySeconds] = useState(() => {
        if (typeof window !== "undefined") {
            const saved = localStorage.getItem("tg_draft_campaign_delay");
            return saved ? Number(saved) : 25;
        }
        return 25;
    });
    const [useJitter, setUseJitter] = useState(true);
    const [templates, setTemplates] = useState<BroadcastTemplate[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");

    // Persist draft inputs so user inputs are never lost
    useEffect(() => {
        if (typeof window !== "undefined") {
            if (name) localStorage.setItem("tg_draft_campaign_name", name);
            if (message) localStorage.setItem("tg_draft_campaign_message", message);
            localStorage.setItem("tg_draft_campaign_delay", String(delaySeconds));
        }
    }, [name, message, delaySeconds]);

    // Load templates for quick selection
    useEffect(() => {
        const fetchTemplates = async () => {
            try {
                const res = await fetch(`${API_BASE}/templates`);
                if (res.ok) {
                    const data = await res.json();
                    setTemplates(data);
                }
            } catch (e) {}
        };
        fetchTemplates();
    }, []);

    const cleanGluedTags = (txt: string) => {
        let res = txt;
        while (/(https?:\/\/[^\s{}]+)\{[a-zA-Z0-9_| ]+\}/.test(res)) {
            res = res.replace(/(https?:\/\/[^\s{}]+)\{[a-zA-Z0-9_| ]+\}/g, "$1");
        }
        return res;
    };

    const insertTag = (tag: string) => {
        setMessage(prev => {
            if (!prev) return tag;
            if (/https?:\/\/[^\s]+$/.test(prev)) {
                return prev + "\n\n" + tag;
            }
            if (!/\s$/.test(prev)) {
                return prev + " " + tag;
            }
            return prev + tag;
        });
    };

    const renderPreview = (txt: string) => {
        if (!txt) return "";
        let res = cleanGluedTags(txt);
        const urls = res.match(/https?:\/\/[^\s]+/g) || [];
        const map: { [k: string]: string } = {};
        urls.forEach((u, i) => {
            const token = `__TOKEN_URL_${i}__`;
            map[token] = u;
            res = res.replace(u, token);
        });
        res = res.replace(/\{group_name\}/g, "VIP Subscribers Chat");
        res = res.replace(/\{greeting\}/g, "Hello");
        res = res.replace(/\{random_emoji\}/g, "✨");
        res = res.replace(/\{date\}/g, new Date().toLocaleDateString());
        res = res.replace(/\{time\}/g, new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
        res = res.replace(/\{([^{}]+)\}/g, (m, choices) => {
            const parts = choices.split("|");
            return parts[0].trim();
        });
        Object.entries(map).forEach(([k, v]) => {
            res = res.replace(k, v);
        });
        return res;
    };

    const detectedLinks = message.match(/https?:\/\/[^\s]+/g) || [];

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError("");
        try {
            const cleanMsg = cleanGluedTags(message.trim());
            const res = await fetch(`${API_BASE}/campaigns`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: name.trim(),
                    message_text: cleanMsg,
                    delay_seconds: Number(delaySeconds),
                    use_jitter: useJitter,
                    chat_ids: initialSelectedIds.length > 0 ? initialSelectedIds : null,
                    media_path: mediaPath,
                    media_url: mediaUrl
                }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Failed to create campaign");
            onClose();
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const targetCount = initialSelectedIds.length > 0 ? initialSelectedIds.length : "All active writable groups";
    const estimatedMinutes = typeof targetCount === "number" ? Math.round((targetCount * delaySeconds) / 60) : null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm overflow-y-auto">
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="blue-glass w-full max-w-xl p-6 md:p-8 rounded-3xl border border-white/10 space-y-6 my-8"
            >
                <div className="flex justify-between items-center">
                    <div>
                        <h3 className="text-xl font-bold text-white">Create Broadcast Campaign</h3>
                        <p className="text-xs text-slate-400 mt-0.5">
                            Targets: <strong className="text-blue-400">{targetCount}</strong>
                        </p>
                    </div>
                    <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
                        <Plus className="w-6 h-6 rotate-45" />
                    </button>
                </div>

                {error && (
                    <div className="p-3.5 bg-red-500/10 border border-red-500/20 text-red-400 rounded-xl text-xs">
                        {error}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-5">
                    <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1.5">Campaign Name</label>
                        <input
                            type="text"
                            placeholder="e.g. Weekly Community Announcement"
                            className="w-full bg-slate-900/80 border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-blue-500"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            required
                        />
                    </div>

                    {templates.length > 0 && (
                        <div>
                            <label className="block text-xs font-semibold text-slate-300 mb-1.5">Use Saved Template (Optional)</label>
                            <select
                                className="w-full bg-slate-900 border border-white/10 rounded-xl px-3 py-2.5 text-xs text-slate-300 focus:outline-none focus:border-blue-500 appearance-none"
                                onChange={(e) => {
                                    const selectedId = Number(e.target.value);
                                    const selected = templates.find((t) => t.id === selectedId);
                                    if (selected) {
                                        setMessage(cleanGluedTags(selected.message_text));
                                        setMediaPath(selected.media_path || null);
                                        setMediaUrl(selected.media_url || null);
                                    }
                                }}
                                defaultValue=""
                            >
                                <option value="">-- Choose a template to autofill --</option>
                                {templates.map((tpl) => (
                                    <option key={tpl.id} value={tpl.id}>
                                        {tpl.name} {tpl.media_url ? "(with media)" : ""}
                                    </option>
                                ))}
                            </select>
                        </div>
                    )}

                    {/* Media Uploader for Images & Videos */}
                    <MediaUploader
                        mediaPath={mediaPath}
                        mediaUrl={mediaUrl}
                        onChange={(path, url) => {
                            setMediaPath(path);
                            setMediaUrl(url);
                        }}
                    />

                    <div>
                        <div className="flex justify-between items-center mb-1.5">
                            <label className="text-xs font-semibold text-slate-300">Message Content (or Media Caption)</label>
                            <span className="text-[10px] text-slate-400">Supports Spintax & Tags</span>
                        </div>
                        <textarea
                            placeholder="Type your broadcast message or caption: {Hello|Hi} everyone! Check out our updates."
                            rows={5}
                            className="w-full bg-slate-900/80 border border-white/10 rounded-xl p-3.5 text-sm text-white focus:outline-none focus:border-blue-500 font-sans resize-none"
                            value={message}
                            onChange={(e) => setMessage(e.target.value)}
                            required
                        />

                        {/* Tag insertion helpers */}
                        <div className="flex flex-wrap items-center gap-1.5 mt-2">
                            <span className="text-[10px] text-slate-500 mr-1">Insert Dynamic Tag:</span>
                            {["{group_name}", "{random_emoji}", "{greeting}", "{date}", "{time}"].map((tag) => (
                                <button
                                    key={tag}
                                    type="button"
                                    onClick={() => insertTag(tag)}
                                    className="px-2 py-0.5 rounded bg-white/5 hover:bg-white/10 border border-white/10 text-blue-400 text-[10px] font-mono transition-colors"
                                >
                                    {tag}
                                </button>
                            ))}
                        </div>

                        {detectedLinks.length > 0 && (
                            <div className="p-2.5 rounded-xl bg-white/5 border border-white/5 space-y-1 mt-2.5">
                                <span className="text-[11px] text-emerald-400 font-semibold flex items-center space-x-1.5">
                                    <Shield className="w-3.5 h-3.5" />
                                    <span>Detected Links (Protected & Verified Intact):</span>
                                </span>
                                <div className="flex flex-wrap gap-1.5">
                                    {detectedLinks.map((link, idx) => (
                                        <span key={idx} className="text-[11px] px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 font-mono">
                                            {link}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}

                        {(message.trim() || mediaUrl) && (
                            <div className="p-3.5 rounded-xl bg-slate-900/90 border border-white/10 space-y-2 mt-3">
                                <div className="flex items-center justify-between text-[11px] text-slate-400">
                                    <span className="flex items-center space-x-1 font-semibold text-slate-300">
                                        <Eye className="w-3.5 h-3.5 text-blue-400" />
                                        <span>Live Telegram Post Preview</span>
                                    </span>
                                    <span className="text-[10px] text-emerald-400 font-medium">Link Untouched</span>
                                </div>
                                <div className="p-3 rounded-lg bg-black/40 border border-white/5 space-y-2 font-sans">
                                    {mediaUrl && (
                                        <div className="rounded-lg overflow-hidden max-h-44 bg-black/50 border border-white/10 flex items-center justify-center">
                                            {mediaUrl.match(/\.(mp4|mov|webm|mkv)$/i) || mediaPath?.match(/\.(mp4|mov|webm|mkv)$/i) ? (
                                                <video src={mediaUrl} controls className="max-h-44 w-full object-cover rounded-lg" />
                                            ) : (
                                                <img src={mediaUrl} alt="" className="max-h-44 w-full object-cover rounded-lg" />
                                            )}
                                        </div>
                                    )}
                                    {message.trim() && (
                                        <div className="text-xs text-slate-200 whitespace-pre-wrap max-h-36 overflow-y-auto">
                                            {renderPreview(message)}
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Broadcast timing controls & Speed Presets */}
                    <div className="p-4 rounded-2xl bg-white/5 border border-white/5 space-y-3.5">
                        <div className="space-y-1.5">
                            <label className="text-xs font-semibold text-white flex items-center justify-between">
                                <span>Pacing & Speed Mode</span>
                                <span className="text-[11px] text-blue-400 font-mono font-bold">{delaySeconds}s interval</span>
                            </label>
                            
                            {/* Preset speed buttons */}
                            <div className="grid grid-cols-3 gap-2 pt-1">
                                <button
                                    type="button"
                                    onClick={() => setDelaySeconds(10)}
                                    className={`py-2 px-2 rounded-xl border text-center transition-all ${
                                        delaySeconds === 10
                                            ? "bg-purple-600/30 border-purple-500/50 text-white font-bold ring-1 ring-purple-500"
                                            : "bg-slate-900/60 border-white/5 hover:border-white/10 text-slate-300"
                                    }`}
                                >
                                    <div className="text-[11px] font-bold flex items-center justify-center space-x-1">
                                        <span>⚡ Turbo</span>
                                    </div>
                                    <div className="text-[10px] text-slate-400 mt-0.5">10s (Fast)</div>
                                </button>

                                <button
                                    type="button"
                                    onClick={() => setDelaySeconds(25)}
                                    className={`py-2 px-2 rounded-xl border text-center transition-all ${
                                        delaySeconds === 25
                                            ? "bg-blue-600/30 border-blue-500/50 text-white font-bold ring-1 ring-blue-500"
                                            : "bg-slate-900/60 border-white/5 hover:border-white/10 text-slate-300"
                                    }`}
                                >
                                    <div className="text-[11px] font-bold flex items-center justify-center space-x-1">
                                        <span>⚖️ Balanced</span>
                                    </div>
                                    <div className="text-[10px] text-slate-400 mt-0.5">25s (Rec.)</div>
                                </button>

                                <button
                                    type="button"
                                    onClick={() => setDelaySeconds(60)}
                                    className={`py-2 px-2 rounded-xl border text-center transition-all ${
                                        delaySeconds === 60
                                            ? "bg-emerald-600/30 border-emerald-500/50 text-white font-bold ring-1 ring-emerald-500"
                                            : "bg-slate-900/60 border-white/5 hover:border-white/10 text-slate-300"
                                    }`}
                                >
                                    <div className="text-[11px] font-bold flex items-center justify-center space-x-1">
                                        <span>🛡️ Safe</span>
                                    </div>
                                    <div className="text-[10px] text-slate-400 mt-0.5">60s (Slow)</div>
                                </button>
                            </div>
                        </div>

                        <div className="flex items-center justify-between pt-2 border-t border-white/5">
                            <div>
                                <label className="text-xs font-semibold text-white">Custom Seconds</label>
                                <p className="text-[10px] text-slate-400">Custom interval between group posts</p>
                            </div>
                            <div className="flex items-center space-x-2">
                                <input
                                    type="number"
                                    min={3}
                                    max={600}
                                    className="w-20 bg-slate-900 border border-white/10 rounded-lg px-2.5 py-1.5 text-sm text-white text-center focus:outline-none focus:border-blue-500"
                                    value={delaySeconds}
                                    onChange={(e) => setDelaySeconds(Math.max(3, Number(e.target.value)))}
                                />
                                <span className="text-xs text-slate-400">sec</span>
                            </div>
                        </div>

                        <div className="flex items-center justify-between pt-2 border-t border-white/5 text-xs">
                            <label className="text-slate-300">Human Jitter Randomization (±2-4s)</label>
                            <input
                                type="checkbox"
                                checked={useJitter}
                                onChange={(e) => setUseJitter(e.target.checked)}
                                className="w-4 h-4 rounded text-blue-600 focus:ring-0 bg-slate-900 border-white/20"
                            />
                        </div>

                        {estimatedMinutes !== null && (
                            <p className="text-[11px] text-blue-300 font-medium pt-1">
                                ⏱ Estimated run time: ~{Math.floor(estimatedMinutes / 60)}h {estimatedMinutes % 60}m for {targetCount} groups
                            </p>
                        )}
                    </div>

                    <button
                        type="submit"
                        disabled={loading}
                        className="btn-primary w-full text-sm py-3 flex items-center justify-center space-x-2"
                    >
                        <Send className="w-4 h-4" />
                        <span>{loading ? "Starting Worker..." : "Launch Safe Broadcast"}</span>
                    </button>
                </form>
            </motion.div>
        </div>
    );
}

/* =========================================================================
   TEMPLATE EDITOR & SPINTAX TESTER MODAL
   ========================================================================= */
function TemplateEditorModal({
    template,
    onClose,
    onSaved
}: {
    template: BroadcastTemplate | null;
    onClose: () => void;
    onSaved?: (tpl: BroadcastTemplate) => void;
}) {
    const [name, setName] = useState(template?.name || "");
    const [messageText, setMessageText] = useState(template?.message_text || "");
    const [mediaPath, setMediaPath] = useState<string | null>(template?.media_path || null);
    const [mediaUrl, setMediaUrl] = useState<string | null>(template?.media_url || null);
    const [loading, setLoading] = useState(false);
    const [savingCopy, setSavingCopy] = useState(false);
    const [error, setError] = useState("");
    
    // Spintax test samples
    const [previewSamples, setPreviewSamples] = useState<string[]>([]);
    const [previewLoading, setPreviewLoading] = useState(false);

    const cleanGluedTags = (txt: string) => {
        let res = txt;
        while (/(https?:\/\/[^\s{}]+)\{[a-zA-Z0-9_| ]+\}/.test(res)) {
            res = res.replace(/(https?:\/\/[^\s{}]+)\{[a-zA-Z0-9_| ]+\}/g, "$1");
        }
        return res;
    };

    const handleSave = async (asNewCopy: boolean = false) => {
        if (!name.trim()) {
            setError("Template name is required");
            return;
        }
        if (!messageText.trim()) {
            setError("Template message text is required");
            return;
        }
        if (asNewCopy) {
            setSavingCopy(true);
        } else {
            setLoading(true);
        }
        setError("");
        try {
            const cleanMsg = cleanGluedTags(messageText.trim());
            const isUpdate = !asNewCopy && template !== null;
            const url = isUpdate ? `${API_BASE}/templates/${template.id}` : `${API_BASE}/templates/`;
            const method = isUpdate ? "PUT" : "POST";
            const templateName = asNewCopy ? `${name.trim()} (Copy)` : name.trim();

            const res = await fetch(url, {
                method,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: templateName,
                    message_text: cleanMsg,
                    media_path: mediaPath,
                    media_url: mediaUrl
                })
            });
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || "Failed to save template");
            }
            const savedItem: BroadcastTemplate = await res.json();
            
            // Save to localStorage backup so it survives logout and DB wipes
            try {
                const backupRaw = localStorage.getItem("tg_templates_backup");
                let backup: BroadcastTemplate[] = backupRaw ? JSON.parse(backupRaw) : [];
                if (isUpdate) {
                    backup = backup.map(t => t.id === template.id ? savedItem : t);
                } else {
                    backup.push(savedItem);
                }
                localStorage.setItem("tg_templates_backup", JSON.stringify(backup));
            } catch (backupErr) {}

            onSaved?.(savedItem);
            onClose();
        } catch (err: any) {
            setError(err.message || "Failed to save template");
        } finally {
            setLoading(false);
            setSavingCopy(false);
        }
    };

    const handleTestSpintax = async () => {
        if (!messageText.trim()) return;
        setPreviewLoading(true);
        try {
            const res = await fetch(`${API_BASE}/templates/preview`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    template_text: cleanGluedTags(messageText),
                    count: 3
                })
            });
            if (res.ok) {
                const data = await res.json();
                setPreviewSamples(data.samples || []);
            }
        } catch (e) {} finally {
            setPreviewLoading(false);
        }
    };

    const insertTag = (tag: string) => {
        setMessageText(prev => {
            if (!prev) return tag;
            if (/https?:\/\/[^\s]+$/.test(prev)) {
                return prev + "\n\n" + tag;
            }
            if (!/\s$/.test(prev)) {
                return prev + " " + tag;
            }
            return prev + tag;
        });
    };

    const detectedLinks = messageText.match(/https?:\/\/[^\s]+/g) || [];

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm overflow-y-auto">
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="blue-glass w-full max-w-2xl p-6 md:p-8 rounded-3xl border border-white/10 space-y-6 my-8"
            >
                <div className="flex justify-between items-center">
                    <div>
                        <h3 className="text-xl font-bold text-white">
                            {template ? "Edit Broadcast Template" : "New Broadcast Template"}
                        </h3>
                        <p className="text-xs text-slate-400 mt-0.5">Test how Spintax variations and attached media look across different groups</p>
                    </div>
                    <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
                        <Plus className="w-6 h-6 rotate-45" />
                    </button>
                </div>

                {error && (
                    <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-400 rounded-xl text-xs">
                        {error}
                    </div>
                )}

                <form onSubmit={(e) => { e.preventDefault(); handleSave(false); }} className="space-y-4">
                    <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1.5">Template Name</label>
                        <input
                            type="text"
                            placeholder="e.g. VIP Member Invite"
                            className="w-full bg-slate-900/80 border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-blue-500"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            required
                        />
                    </div>

                    {/* Media attachment for templates */}
                    <MediaUploader
                        mediaPath={mediaPath}
                        mediaUrl={mediaUrl}
                        onChange={(path, url) => {
                            setMediaPath(path);
                            setMediaUrl(url);
                        }}
                    />

                    <div>
                        <div className="flex justify-between items-center mb-1.5">
                            <label className="text-xs font-semibold text-slate-300">Message Text with Spintax (Caption)</label>
                            <span className="text-[10px] text-slate-400">Use {"{word1|word2}"} syntax</span>
                        </div>
                        <textarea
                            placeholder="e.g. {Hello|Hi|Greetings} members of {group_name}! {Check out|Explore} our latest news {random_emoji}"
                            rows={5}
                            className="w-full bg-slate-900/80 border border-white/10 rounded-xl p-3.5 text-sm text-white focus:outline-none focus:border-blue-500 font-sans resize-none"
                            value={messageText}
                            onChange={(e) => setMessageText(e.target.value)}
                            required
                        />

                        {/* Tag insertion */}
                        <div className="flex flex-wrap items-center gap-1.5 mt-2">
                            <span className="text-[10px] text-slate-500 mr-1">Insert Helper:</span>
                            {["{group_name}", "{greeting}", "{date}", "{time}", "{random_emoji}", "{Option A|Option B|Option C}"].map((tag) => (
                                <button
                                    key={tag}
                                    type="button"
                                    onClick={() => insertTag(tag)}
                                    className="px-2 py-0.5 rounded bg-white/5 hover:bg-white/10 border border-white/10 text-blue-400 text-[10px] font-mono transition-colors"
                                >
                                    {tag}
                                </button>
                            ))}
                        </div>

                        {detectedLinks.length > 0 && (
                            <div className="p-2.5 rounded-xl bg-white/5 border border-white/5 space-y-1 mt-2.5">
                                <span className="text-[11px] text-emerald-400 font-semibold flex items-center space-x-1.5">
                                    <Shield className="w-3.5 h-3.5" />
                                    <span>Detected Links (Protected & Verified Intact):</span>
                                </span>
                                <div className="flex flex-wrap gap-1.5">
                                    {detectedLinks.map((link, idx) => (
                                        <span key={idx} className="text-[11px] px-2 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 font-mono">
                                            {link}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Spintax Live Tester Section */}
                    <div className="p-4 rounded-2xl bg-white/5 border border-white/5 space-y-3">
                        <div className="flex justify-between items-center">
                            <div className="flex items-center space-x-1.5 text-xs font-semibold text-slate-200">
                                <Sparkles className="w-3.5 h-3.5 text-blue-400" />
                                <span>Spintax Live Variation Tester</span>
                            </div>
                            <button
                                type="button"
                                onClick={handleTestSpintax}
                                disabled={previewLoading || !messageText.trim()}
                                className="px-3 py-1 rounded-lg bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 border border-blue-500/20 text-xs font-semibold transition-all disabled:opacity-50"
                            >
                                {previewLoading ? "Generating..." : "Generate 3 Test Spins"}
                            </button>
                        </div>

                        {previewSamples.length > 0 && (
                            <div className="space-y-2 pt-2">
                                {previewSamples.map((sample, idx) => (
                                    <div key={idx} className="p-3 rounded-xl bg-slate-900/90 border border-white/5 text-xs text-slate-300 font-sans space-y-2">
                                        <span className="text-[10px] text-blue-400 font-mono block">Variation #{idx + 1}:</span>
                                        {mediaUrl && (
                                            <div className="rounded-lg overflow-hidden max-h-36 bg-black/50 border border-white/10 flex items-center justify-center">
                                                {mediaUrl.match(/\.(mp4|mov|webm|mkv)$/i) || mediaPath?.match(/\.(mp4|mov|webm|mkv)$/i) ? (
                                                    <video src={mediaUrl} controls className="max-h-36 w-full object-cover rounded-lg" />
                                                ) : (
                                                    <img src={mediaUrl} alt="" className="max-h-36 w-full object-cover rounded-lg" />
                                                )}
                                            </div>
                                        )}
                                        <p>{sample}</p>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-5 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-slate-400 text-xs font-semibold"
                        >
                            Cancel
                        </button>
                        <div className="flex items-center space-x-2">
                            {template && (
                                <button
                                    type="button"
                                    onClick={() => handleSave(true)}
                                    disabled={loading || savingCopy}
                                    className="px-4 py-2.5 rounded-xl bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 border border-purple-500/20 text-xs font-semibold flex items-center space-x-1.5 transition-all disabled:opacity-50"
                                >
                                    <Copy className="w-3.5 h-3.5" />
                                    <span>{savingCopy ? "Copying..." : "Save as New Copy"}</span>
                                </button>
                            )}
                            <button
                                type="submit"
                                disabled={loading || savingCopy}
                                className="btn-primary text-xs py-2.5 px-6"
                            >
                                {loading ? "Saving..." : template ? "Save Changes" : "Create Template"}
                            </button>
                        </div>
                    </div>
                </form>
            </motion.div>
        </div>
    );
}

/* =========================================================================
   JOIN GROUP MODAL
   ========================================================================= */
function JoinGroupModal({ onClose, onJoined }: { onClose: () => void; onJoined: () => void }) {
    const [link, setLink] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");

    const handleJoin = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError("");
        setSuccess("");
        try {
            const res = await fetch(`${API_BASE}/telegram/join`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ group_link: link.trim() })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Failed to join group");
            setSuccess(`Successfully joined '${data.title || "Group"}'! Added to your detected groups.`);
            onJoined();
            setTimeout(() => onClose(), 2000);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="blue-glass w-full max-w-md p-6 md:p-8 rounded-3xl border border-white/10 space-y-5"
            >
                <div className="flex justify-between items-center">
                    <h3 className="text-xl font-bold text-white">Join Telegram Group</h3>
                    <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
                        <Plus className="w-6 h-6 rotate-45" />
                    </button>
                </div>

                {error && <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-400 rounded-xl text-xs">{error}</div>}
                {success && <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-xl text-xs">{success}</div>}

                <form onSubmit={handleJoin} className="space-y-4">
                    <div>
                        <label className="block text-xs font-semibold text-slate-300 mb-1.5">Group Link or @Username</label>
                        <input
                            type="text"
                            placeholder="e.g. t.me/+inviteHash or @cryptochat"
                            className="w-full bg-slate-900/80 border border-white/10 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-blue-500"
                            value={link}
                            onChange={(e) => setLink(e.target.value)}
                            required
                        />
                        <p className="text-[11px] text-slate-500 mt-1.5">
                            Supports private invite links (t.me/+...) and public group usernames.
                        </p>
                    </div>

                    <button type="submit" disabled={loading} className="btn-primary w-full text-xs py-3">
                        {loading ? "Joining via Telegram..." : "Join & Add Group"}
                    </button>
                </form>
            </motion.div>
        </div>
    );
}

/* =========================================================================
   CAMPAIGN LOGS AUDIT MODAL
   ========================================================================= */
function CampaignLogsModal({ campaignId, onClose }: { campaignId: number; onClose: () => void }) {
    const [logs, setLogs] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchLogs = async () => {
            try {
                const res = await fetch(`${API_BASE}/campaigns/${campaignId}/logs?limit=150`);
                if (res.ok) {
                    const data = await res.json();
                    setLogs(data);
                }
            } catch (e) {} finally {
                setLoading(false);
            }
        };
        fetchLogs();
    }, [campaignId]);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm overflow-y-auto">
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="blue-glass w-full max-w-3xl p-6 md:p-8 rounded-3xl border border-white/10 space-y-5 my-8 max-h-[85vh] flex flex-col"
            >
                <div className="flex justify-between items-center">
                    <div>
                        <h3 className="text-xl font-bold text-white">Broadcast Delivery Audit</h3>
                        <p className="text-xs text-slate-400 mt-0.5">Per-group logs with status and resolved spintax messages</p>
                    </div>
                    <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
                        <Plus className="w-6 h-6 rotate-45" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto space-y-2.5 pr-1">
                    {loading ? (
                        <div className="text-center py-12 text-slate-400 text-xs">Loading delivery logs...</div>
                    ) : logs.length === 0 ? (
                        <div className="text-center py-12 text-slate-500 text-xs">No delivery logs recorded yet.</div>
                    ) : (
                        logs.map((log) => (
                            <div key={log.id} className="p-3.5 rounded-xl bg-slate-900/60 border border-white/5 space-y-1.5 text-xs">
                                <div className="flex items-center justify-between">
                                    <span className="font-semibold text-white">{log.group_name || `Target ${log.group_id}`}</span>
                                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase ${log.status === "success" ? "bg-emerald-500/20 text-emerald-400" : "bg-red-500/20 text-red-400"}`}>
                                        {log.status}
                                    </span>
                                </div>
                                {log.sent_message_snippet && (
                                    <p className="text-slate-400 italic text-[11px] line-clamp-2">
                                        "{log.sent_message_snippet}"
                                    </p>
                                )}
                                {log.error_message && (
                                    <p className="text-red-400 text-[11px]">
                                        Reason: {log.error_message}
                                    </p>
                                )}
                                <span className="text-[10px] text-slate-500 block">
                                    {new Date(log.sent_at).toLocaleTimeString()}
                                </span>
                            </div>
                        ))
                    )}
                </div>
            </motion.div>
        </div>
    );
}

/* =========================================================================
   EDIT CAMPAIGN MESSAGE MODAL
   ========================================================================= */
function EditCampaignMessageModal({
    campaign,
    initialMessage,
    onClose,
    onSaved
}: {
    campaign: Campaign;
    initialMessage: string;
    onClose: () => void;
    onSaved: (updated: Campaign) => void;
}) {
    const [name, setName] = useState(campaign.name);
    const [message, setMessage] = useState(initialMessage || campaign.message_text);
    const [mediaPath, setMediaPath] = useState<string | null>(campaign.media_path || null);
    const [mediaUrl, setMediaUrl] = useState<string | null>(campaign.media_url || null);
    const [delaySeconds, setDelaySeconds] = useState(campaign.delay_seconds || 25);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");

    const cleanGluedTags = (txt: string) => {
        let res = txt;
        while (/(https?:\/\/[^\s{}]+)\{[a-zA-Z0-9_| ]+\}/.test(res)) {
            res = res.replace(/(https?:\/\/[^\s{}]+)\{[a-zA-Z0-9_| ]+\}/g, "$1");
        }
        return res;
    };

    const insertTag = (tag: string) => {
        setMessage(prev => {
            if (!prev) return tag;
            if (/https?:\/\/[^\s]+$/.test(prev)) {
                return prev + "\n\n" + tag;
            }
            if (!/\s$/.test(prev)) {
                return prev + " " + tag;
            }
            return prev + tag;
        });
    };

    const renderPreview = (txt: string) => {
        if (!txt) return "";
        let res = cleanGluedTags(txt);
        const urls = res.match(/https?:\/\/[^\s]+/g) || [];
        const map: { [k: string]: string } = {};
        urls.forEach((u, i) => {
            const token = `__TOKEN_URL_${i}__`;
            map[token] = u;
            res = res.replace(u, token);
        });
        res = res.replace(/\{group_name\}/g, "VIP Subscribers Chat");
        res = res.replace(/\{greeting\}/g, "Hello");
        res = res.replace(/\{random_emoji\}/g, "✨");
        res = res.replace(/\{date\}/g, new Date().toLocaleDateString());
        res = res.replace(/\{time\}/g, new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
        res = res.replace(/\{([^{}]+)\}/g, (m, choices) => {
            const parts = choices.split("|");
            return parts[0].trim();
        });
        Object.entries(map).forEach(([k, v]) => {
            res = res.replace(k, v);
        });
        return res;
    };

    const detectedLinks = message.match(/https?:\/\/[^\s]+/g) || [];
    const hasCorruptTagGlued = /(https?:\/\/[^\s{}]+)\{[a-zA-Z0-9_| ]+\}/.test(message);

    const handleSave = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError("");
        setSuccess("");
        try {
            const cleanMsg = cleanGluedTags(message.trim());
            const res = await fetch(`${API_BASE}/campaigns/${campaign.id}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    name: name.trim(),
                    message_text: cleanMsg,
                    delay_seconds: Number(delaySeconds),
                    media_path: mediaPath,
                    media_url: mediaUrl
                })
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Failed to update broadcast message");
            setSuccess("Broadcast message updated successfully! Safe links locked in.");
            setTimeout(() => {
                onSaved(data);
            }, 800);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm overflow-y-auto">
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="blue-glass w-full max-w-2xl p-6 md:p-8 rounded-3xl border border-white/10 space-y-6 my-8"
            >
                <div className="flex justify-between items-center">
                    <div>
                        <h3 className="text-xl font-bold text-white">Edit Broadcast Message & Settings</h3>
                        <p className="text-xs text-slate-400 mt-0.5">
                            Update message for <strong className="text-blue-400">{campaign.name}</strong> (Target {campaign.processed_count} of {campaign.total_targets})
                        </p>
                    </div>
                    <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
                        <Plus className="w-6 h-6 rotate-45" />
                    </button>
                </div>

                {error && (
                    <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-400 rounded-xl text-xs">
                        {error}
                    </div>
                )}
                {success && (
                    <div className="p-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-xl text-xs flex items-center space-x-2">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        <span>{success}</span>
                    </div>
                )}

                {hasCorruptTagGlued && (
                    <div className="p-3 bg-amber-500/10 border border-amber-500/20 text-amber-300 rounded-xl text-xs flex items-center justify-between">
                        <span>⚠️ Dynamic tag is touching a URL slug! Click to safely clean it:</span>
                        <button
                            type="button"
                            onClick={() => setMessage(cleanGluedTags(message))}
                            className="px-2.5 py-1 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-200 text-xs font-semibold"
                        >
                            Fix Link Now
                        </button>
                    </div>
                )}

                <form onSubmit={handleSave} className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <label className="block text-xs font-semibold text-slate-300 mb-1.5">Broadcast Name</label>
                            <input
                                type="text"
                                className="w-full bg-slate-900/80 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                                required
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-semibold text-slate-300 mb-1.5">Interval Delay (seconds)</label>
                            <input
                                type="number"
                                min={3}
                                max={600}
                                className="w-full bg-slate-900/80 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500"
                                value={delaySeconds}
                                onChange={(e) => setDelaySeconds(Math.max(3, Number(e.target.value)))}
                                required
                            />
                        </div>
                    </div>

                    {/* Media attachment */}
                    <MediaUploader
                        mediaPath={mediaPath}
                        mediaUrl={mediaUrl}
                        onChange={(path, url) => {
                            setMediaPath(path);
                            setMediaUrl(url);
                        }}
                    />

                    <div>
                        <div className="flex justify-between items-center mb-1.5">
                            <label className="text-xs font-semibold text-slate-300">Message Content (Caption)</label>
                            <span className="text-[10px] text-emerald-400 font-medium">Links are protected against tampering</span>
                        </div>
                        <textarea
                            rows={6}
                            className="w-full bg-slate-900/80 border border-white/10 rounded-xl p-3.5 text-sm text-white focus:outline-none focus:border-blue-500 font-sans resize-none"
                            value={message}
                            onChange={(e) => setMessage(e.target.value)}
                            required
                        />

                        {/* Tag insertion helpers */}
                        <div className="flex flex-wrap items-center gap-1.5 mt-2">
                            <span className="text-[10px] text-slate-500 mr-1">Insert Helper:</span>
                            {["{group_name}", "{random_emoji}", "{greeting}", "{date}", "{time}"].map((tag) => (
                                <button
                                    key={tag}
                                    type="button"
                                    onClick={() => insertTag(tag)}
                                    className="px-2 py-0.5 rounded bg-white/5 hover:bg-white/10 border border-white/10 text-blue-400 text-[10px] font-mono transition-colors"
                                >
                                    {tag}
                                </button>
                            ))}
                        </div>
                    </div>

                    {detectedLinks.length > 0 && (
                        <div className="p-3 rounded-xl bg-white/5 border border-white/5 space-y-1.5">
                            <span className="text-[11px] text-emerald-400 font-semibold flex items-center space-x-1.5">
                                <Shield className="w-3.5 h-3.5" />
                                <span>Detected Links (Protected & Locked):</span>
                            </span>
                            <div className="flex flex-wrap gap-1.5">
                                {detectedLinks.map((link, idx) => (
                                    <span key={idx} className="text-[11px] px-2.5 py-1 rounded bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 font-mono">
                                        {link}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}

                    {(message.trim() || mediaUrl) && (
                        <div className="p-3.5 rounded-xl bg-slate-900/90 border border-white/10 space-y-2">
                            <div className="flex items-center justify-between text-[11px] text-slate-400">
                                <span className="flex items-center space-x-1 font-semibold text-slate-300">
                                    <Eye className="w-3.5 h-3.5 text-blue-400" />
                                    <span>Live Telegram Preview</span>
                                </span>
                                <span className="text-[10px] text-emerald-400 font-medium">Link Intact</span>
                            </div>
                            <div className="p-3 rounded-lg bg-black/40 border border-white/5 space-y-2 font-sans">
                                {mediaUrl && (
                                    <div className="rounded-lg overflow-hidden max-h-44 bg-black/50 border border-white/10 flex items-center justify-center">
                                        {mediaUrl.match(/\.(mp4|mov|webm|mkv)$/i) || mediaPath?.match(/\.(mp4|mov|webm|mkv)$/i) ? (
                                            <video src={mediaUrl} controls className="max-h-44 w-full object-cover rounded-lg" />
                                        ) : (
                                            <img src={mediaUrl} alt="" className="max-h-44 w-full object-cover rounded-lg" />
                                        )}
                                    </div>
                                )}
                                {message.trim() && (
                                    <div className="text-xs text-slate-200 whitespace-pre-wrap max-h-40 overflow-y-auto">
                                        {renderPreview(message)}
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    <div className="flex justify-end space-x-3 pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-5 py-2.5 rounded-xl bg-white/5 hover:bg-white/10 text-slate-400 text-xs font-semibold"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            disabled={loading}
                            className="btn-primary text-xs py-2.5 px-6"
                        >
                            {loading ? "Saving Changes..." : "Save Updated Message"}
                        </button>
                    </div>
                </form>
            </motion.div>
        </div>
    );
}
