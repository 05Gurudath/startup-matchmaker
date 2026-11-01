
"use client";

import { useCallback, useEffect, useState } from "react";

const API = "http://127.0.0.1:8000";

type User = {
  user_id: number;
  name: string;
  email: string;
  role: string;
};

type Startup = {
  startup_id: number;
  name: string;
  description: string | null;
  industry_name: string;
  stage: string;
  location: string;
  funding_required: number | null;
  founded_year: number | null;
};

type Deck = {
  deck_id: number;
  startup_id: number;
  file_name: string;
  file_type: string;
  upload_date: string;
  version: string;
  analysis_status: string;
};

type Chunk = {
  content: string;
  section: string;
  chunk_number: number | null;
};

type Analysis = {
  deck: Deck;
  total_chunks: number;
  total_sections: number;
  sections: string[];
  chunks: Chunk[];
};

type Match = {
  match_id: number;
  startup_id: number;
  investor_id: number;
  investor_name: string;
  organization: string;
  investor_type: string;
  match_score: number;
  industry_score: number | null;
  stage_score: number | null;
  investment_score: number | null;
  location_score: number | null;
  similarity_score: number | null;
  generated_at: string;
};

type Tab = "Overview" | "Pitch Deck Analysis" | "Investor Matching";

export default function Home() {
  const [token, setToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [authReady, setAuthReady] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState("");

  const [activeTab, setActiveTab] = useState<Tab>("Overview");
  const [startupId, setStartupId] = useState("6");
  const [startup, setStartup] = useState<Startup | null>(null);
  const [decks, setDecks] = useState<Deck[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [matches, setMatches] = useState<Match[]>([]);

  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [matching, setMatching] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  // Restore and verify an existing login.
  useEffect(() => {
    async function restoreSession() {
      const savedToken = localStorage.getItem("startupmatch_token");

      if (!savedToken) {
        setAuthReady(true);
        return;
      }

      try {
        const response = await fetch(`${API}/auth/me`, {
          headers: {
            Authorization: `Bearer ${savedToken}`,
          },
        });

        if (!response.ok) {
          throw new Error("Session expired");
        }

        const data = await response.json();
        setToken(savedToken);
        setUser(data.user);
      } catch {
        localStorage.removeItem("startupmatch_token");
      } finally {
        setAuthReady(true);
      }
    }

    restoreSession();
  }, []);

  // Login using the existing backend authentication API.
  async function handleLogin(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoginLoading(true);
    setLoginError("");

    try {
      const response = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email, password }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Login failed.");
      }

      localStorage.setItem("startupmatch_token", data.access_token);
      setToken(data.access_token);
      setUser(data.user);
      setPassword("");
    } catch (err) {
      setLoginError(
        err instanceof Error ? err.message : "Unable to login."
      );
    } finally {
      setLoginLoading(false);
    }
  }

  function logout() {
    localStorage.removeItem("startupmatch_token");
    setToken("");
    setUser(null);
    setStartup(null);
    setDecks([]);
    setAnalysis(null);
    setMatches([]);
    setError("");
    setMessage("");
    setActiveTab("Overview");
  }

  // Attach the JWT to all protected API requests.
  const authFetch = useCallback(
    async (url: string, options: RequestInit = {}) => {
      const headers = new Headers(options.headers);
      headers.set("Authorization", `Bearer ${token}`);

      return fetch(url, {
        ...options,
        headers,
      });
    },
    [token]
  );

  const loadDashboard = useCallback(async () => {
    const id = Number(startupId);

    if (!Number.isInteger(id) || id <= 0) {
      setError("Enter a valid startup ID.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const [startupResponse, decksResponse, matchesResponse] =
        await Promise.all([
          authFetch(`${API}/startups/${id}`),
          authFetch(`${API}/pitch-decks/${id}`),
          authFetch(`${API}/matches/${id}`),
        ]);

      if (!startupResponse.ok) {
        const data = await startupResponse.json();
        throw new Error(data.detail || `Startup request failed: ${startupResponse.status}`);
      }

      if (!decksResponse.ok) {
        const data = await decksResponse.json();
        throw new Error(data.detail || `Pitch deck request failed: ${decksResponse.status}`);
      }

      if (!matchesResponse.ok) {
        const data = await matchesResponse.json();
        throw new Error(data.detail || `Matches request failed: ${matchesResponse.status}`);
      }

      const startupData = await startupResponse.json();
      const decksData = await decksResponse.json();
      const matchesData = await matchesResponse.json();

      setStartup(startupData);
      setDecks(decksData.pitch_decks || []);
      setMatches(matchesData.matches || []);

      const latestDeck = (decksData.pitch_decks || [])[0];

      if (latestDeck) {
        const analysisResponse = await authFetch(
          `${API}/pitch-decks/${id}/analysis/${latestDeck.deck_id}`
        );

        if (analysisResponse.ok) {
          setAnalysis(await analysisResponse.json());
        } else {
          setAnalysis(null);
        }
      } else {
        setAnalysis(null);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to connect to backend."
      );
    } finally {
      setLoading(false);
    }
  }, [startupId, authFetch]);

  useEffect(() => {
    if (token) {
      loadDashboard();
    }
  }, [token, loadDashboard]);

  async function uploadDeck() {
    if (!file) {
      setMessage("Please select a PDF file first.");
      return;
    }

    if (
      file.type !== "application/pdf" &&
      !file.name.toLowerCase().endsWith(".pdf")
    ) {
      setMessage("Only PDF files are supported.");
      return;
    }

    if (file.size > 15 * 1024 * 1024) {
      setMessage("The PDF must not exceed 15 MB.");
      return;
    }

    setUploading(true);
    setMessage("");
    setError("");

    try {
      const formData = new FormData();
      formData.append("startup_id", startupId);
      formData.append("file", file);

      const response = await authFetch(`${API}/upload-pitch-deck`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Pitch deck upload failed.");
      }

      setFile(null);
      setMessage("Pitch deck uploaded and analyzed successfully.");
      await loadDashboard();
      setActiveTab("Pitch Deck Analysis");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function generateMatches() {
    if (!startupId || Number(startupId) <= 0) {
      setMessage("Enter a valid startup ID.");
      return;
    }

    setMatching(true);
    setMessage("");
    setError("");

    try {
      const response = await authFetch(
        `${API}/generate-matches/${startupId}`,
        { method: "POST" }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Investor matching failed.");
      }

      await loadDashboard();
      setMessage("Investor matching completed successfully.");
      setActiveTab("Investor Matching");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to generate matches."
      );
    } finally {
      setMatching(false);
    }
  }

  function score(value: number | null | undefined) {
    return value == null ? "N/A" : `${Number(value).toFixed(2)}%`;
  }

  const navigation: Tab[] = [
    "Overview",
    "Pitch Deck Analysis",
    "Investor Matching",
  ];

  // Authentication screen.
  if (!authReady) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100">
        <p className="text-slate-600">Checking login...</p>
      </div>
    );
  }

  if (!token || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
        <form
          onSubmit={handleLogin}
          className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-lg"
        >
          <div className="mb-6 text-center">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-xl bg-indigo-600 text-2xl font-bold text-white">
              S
            </div>
            <h1 className="mt-4 text-2xl font-bold text-slate-800">
              StartupMatch
            </h1>
            <p className="mt-2 text-sm text-slate-500">
              AI Investor Platform
            </p>
          </div>

          <h2 className="mb-5 text-xl font-semibold text-slate-800">
            Login to your account
          </h2>

          {loginError && (
            <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {loginError}
            </div>
          )}

          <label className="mb-2 block text-sm font-medium text-slate-700">
            Email
          </label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Enter your email"
            className="mb-5 w-full rounded-lg border border-slate-300 px-4 py-3 outline-none focus:border-indigo-500"
          />

          <label className="mb-2 block text-sm font-medium text-slate-700">
            Password
          </label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter your password"
            className="mb-6 w-full rounded-lg border border-slate-300 px-4 py-3 outline-none focus:border-indigo-500"
          />

          <button
            type="submit"
            disabled={loginLoading}
            className="w-full rounded-lg bg-indigo-600 px-4 py-3 font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {loginLoading ? "Logging in..." : "Login"}
          </button>
        </form>
      </div>
    );
  }

  // Investor accounts do not have access to private startup pitch decks.
  if (user.role === "Investor") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100 px-4">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow">
          <h1 className="text-2xl font-bold">Welcome, {user.name}</h1>
          <p className="mt-3 text-slate-600">
            You are logged in as an Investor. The private startup dashboard
            is not available to this role.
          </p>
          <button
            onClick={logout}
            className="mt-6 rounded-lg bg-indigo-600 px-6 py-3 font-semibold text-white"
          >
            Logout
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#f5f7fb] text-slate-800">
      <aside className="fixed left-0 top-0 z-20 hidden h-screen w-64 border-r border-slate-200 bg-white p-6 lg:block">
        <div className="mb-12 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 text-xl font-bold text-white">
            S
          </div>
          <div>
            <h1 className="text-lg font-bold">StartupMatch</h1>
            <p className="text-xs text-slate-400">AI Investor Platform</p>
          </div>
        </div>

        <p className="mb-4 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Workspace
        </p>

        <div className="space-y-2">
          {navigation.map((item) => (
            <button
              key={item}
              onClick={() => setActiveTab(item)}
              className={`w-full rounded-xl px-4 py-3 text-left text-sm font-medium ${
                activeTab === item
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-slate-500 hover:bg-slate-50"
              }`}
            >
              {item}
            </button>
          ))}
        </div>

        <div className="absolute bottom-7 left-6 right-6 rounded-2xl bg-indigo-50 p-4">
          <p className="text-sm font-semibold text-indigo-900">
            AI-powered matching
          </p>
          <p className="mt-1 text-xs leading-5 text-indigo-700">
            Analyze startup pitch decks and discover compatible investors.
          </p>
        </div>
      </aside>

      <main className="min-h-screen lg:ml-64">
        <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 bg-white px-6 py-5 md:px-10">
          <div>
            <p className="text-sm text-slate-400">
              StartupMatch / {activeTab}
            </p>
            <h2 className="mt-1 text-xl font-bold">
              {activeTab === "Overview" ? "Startup Dashboard" : activeTab}
            </h2>
          </div>

          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-sm font-semibold">{user.name}</p>
              <p className="text-xs text-slate-400">{user.role}</p>
            </div>
            <button
              onClick={logout}
              className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium hover:bg-slate-50"
            >
              Logout
            </button>
          </div>
        </header>

        <div className="border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
          <div className="flex gap-2 overflow-x-auto">
            {navigation.map((item) => (
              <button
                key={item}
                onClick={() => setActiveTab(item)}
                className={`shrink-0 rounded-lg px-3 py-2 text-xs font-medium ${
                  activeTab === item
                    ? "bg-indigo-100 text-indigo-700"
                    : "bg-slate-50 text-slate-500"
                }`}
              >
                {item}
              </button>
            ))}
          </div>
        </div>

        <div className="p-6 md:p-10">
          {error && (
            <div className="mb-5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              {error}
            </div>
          )}

          {message && (
            <div className="mb-5 rounded-xl border border-green-200 bg-green-50 p-4 text-sm text-green-800">
              {message}
            </div>
          )}

          {loading && (
            <div className="mb-5 rounded-xl bg-indigo-50 p-4 text-sm text-indigo-700">
              Loading startup data from the backend...
            </div>
          )}

          {activeTab === "Overview" && (
            <>
              <div className="mb-8">
                <p className="text-sm font-medium text-indigo-600">
                  WELCOME TO STARTUPMATCH
                </p>
                <h1 className="mt-2 text-3xl font-bold tracking-tight">
                  Find the right investors for your startup.
                </h1>
                <p className="mt-2 text-slate-500">
                  Upload your pitch deck, analyze your business and discover
                  potential investors using AI.
                </p>
              </div>

              <div className="mb-8 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
                <div className="rounded-2xl border bg-white p-6 shadow-sm">
                  <p className="text-sm text-slate-500">Startup</p>
                  <p className="mt-3 text-xl font-bold">
                    {startup?.name || "Not loaded"}
                  </p>
                  <p className="mt-2 text-xs text-slate-400">
                    {startup?.industry_name || "Industry unavailable"} · ID {startupId}
                  </p>
                  <input
                    type="number"
                    min="1"
                    value={startupId}
                    onChange={(e) => setStartupId(e.target.value)}
                    className="mt-3 w-28 rounded-lg border px-3 py-2 font-semibold"
                  />
                  <button
                    onClick={loadDashboard}
                    className="ml-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm text-white"
                  >
                    Load
                  </button>
                </div>

                <div className="rounded-2xl border bg-white p-6 shadow-sm">
                  <p className="text-sm text-slate-500">Pitch Decks</p>
                  <p className="mt-3 text-3xl font-bold text-indigo-600">
                    {decks.length}
                  </p>
                  <p className="mt-2 text-xs text-slate-400">
                    Uploaded PDF records
                  </p>
                </div>

                <div className="rounded-2xl border bg-white p-6 shadow-sm">
                  <p className="text-sm text-slate-500">Investor Matches</p>
                  <p className="mt-3 text-3xl font-bold text-indigo-600">
                    {matches.length}
                  </p>
                  <p className="mt-2 text-xs text-slate-400">
                    Saved matching results
                  </p>
                </div>
              </div>

              <section className="mb-8 rounded-2xl border bg-white p-6 shadow-sm">
                <h2 className="text-xl font-bold">Startup Information</h2>
                {startup ? (
                  <div className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                    {[
                      ["Startup Name", startup.name],
                      ["Industry", startup.industry_name],
                      ["Stage", startup.stage],
                      ["Location", startup.location],
                      ["Founded Year", startup.founded_year ?? "Not available"],
                      [
                        "Funding Required",
                        startup.funding_required == null
                          ? "Not available"
                          : startup.funding_required.toLocaleString(),
                      ],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-xl bg-slate-50 p-4">
                        <p className="text-xs text-slate-400">{label}</p>
                        <p className="mt-2 font-semibold">{String(value)}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="mt-4 text-sm text-slate-500">
                    Startup information is not available.
                  </p>
                )}
              </section>

              <div className="grid gap-6 xl:grid-cols-2">
                <section className="rounded-2xl border bg-white p-6 shadow-sm">
                  <div className="text-3xl">📄</div>
                  <h2 className="mt-4 text-xl font-bold">Upload Pitch Deck</h2>
                  <p className="mt-2 text-sm text-slate-500">
                    Upload your startup presentation in PDF format.
                  </p>
                  <label className="mt-6 flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-indigo-200 bg-indigo-50/40 p-6 text-center">
                    <span className="text-3xl">☁️</span>
                    <span className="mt-3 break-all text-sm font-semibold">
                      {file ? file.name : "Click to select your PDF"}
                    </span>
                    <span className="mt-2 text-xs text-slate-400">
                      PDF format · Maximum 15 MB
                    </span>
                    <input
                      type="file"
                      accept=".pdf,application/pdf"
                      className="hidden"
                      onChange={(e) => setFile(e.target.files?.[0] || null)}
                    />
                  </label>
                  <button
                    onClick={uploadDeck}
                    disabled={uploading || !file}
                    className="mt-5 w-full rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white disabled:opacity-50"
                  >
                    {uploading ? "Uploading and analyzing..." : "Upload Pitch Deck"}
                  </button>
                </section>

                <section className="rounded-2xl border bg-white p-6 shadow-sm">
                  <div className="text-3xl">✨</div>
                  <h2 className="mt-4 text-xl font-bold">AI Investor Matching</h2>
                  <p className="mt-2 text-sm text-slate-500">
                    Discover investors using industry, stage, investment,
                    location and pitch deck semantic similarity.
                  </p>
                  <div className="my-6 space-y-3 text-sm">
                    {[
                      "Industry compatibility",
                      "Startup stage compatibility",
                      "Investment range compatibility",
                      "Location compatibility",
                      "Pitch deck semantic similarity",
                    ].map((item) => (
                      <div key={item}>
                        <span className="mr-2 text-green-500">✓</span>
                        {item}
                      </div>
                    ))}
                  </div>
                  <button
                    onClick={generateMatches}
                    disabled={matching || loading}
                    className="w-full rounded-xl bg-slate-900 px-5 py-3 font-semibold text-white disabled:opacity-50"
                  >
                    {matching ? "Finding investors..." : "Generate Investor Matches"}
                  </button>
                </section>
              </div>
            </>
          )}

          {activeTab === "Pitch Deck Analysis" && (
            <>
              <div className="mb-8">
                <p className="text-sm font-medium text-indigo-600">
                  DOCUMENT INTELLIGENCE
                </p>
                <h1 className="mt-2 text-3xl font-bold">Pitch Deck Analysis</h1>
                <p className="mt-2 text-slate-500">
                  View uploaded pitch decks and their extracted content.
                </p>
              </div>

              <div className="mb-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
                <div className="rounded-2xl border bg-white p-6 shadow-sm">
                  <p className="text-sm text-slate-500">Uploaded Decks</p>
                  <p className="mt-3 text-3xl font-bold text-indigo-600">{decks.length}</p>
                </div>
                <div className="rounded-2xl border bg-white p-6 shadow-sm">
                  <p className="text-sm text-slate-500">Latest Deck ID</p>
                  <p className="mt-3 text-3xl font-bold">{analysis?.deck.deck_id ?? "—"}</p>
                </div>
                <div className="rounded-2xl border bg-white p-6 shadow-sm">
                  <p className="text-sm text-slate-500">Extracted Chunks</p>
                  <p className="mt-3 text-3xl font-bold">{analysis?.total_chunks ?? 0}</p>
                </div>
              </div>

              <section className="mb-6 rounded-2xl border bg-white p-6 shadow-sm">
                <h2 className="text-xl font-bold">Uploaded Pitch Decks</h2>
                {decks.length === 0 ? (
                  <p className="mt-5 text-sm text-slate-500">
                    No pitch decks have been uploaded for this startup.
                  </p>
                ) : (
                  <div className="mt-5 overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead>
                        <tr className="border-b text-slate-500">
                          <th className="p-3">Deck ID</th>
                          <th className="p-3">Filename</th>
                          <th className="p-3">Version</th>
                          <th className="p-3">Status</th>
                          <th className="p-3">Uploaded</th>
                        </tr>
                      </thead>
                      <tbody>
                        {decks.map((deck) => (
                          <tr key={deck.deck_id} className="border-b">
                            <td className="p-3">{deck.deck_id}</td>
                            <td className="p-3">{deck.file_name}</td>
                            <td className="p-3">{deck.version}</td>
                            <td className="p-3">{deck.analysis_status}</td>
                            <td className="p-3">
                              {new Date(deck.upload_date).toLocaleString()}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section className="rounded-2xl border bg-white p-6 shadow-sm">
                <h2 className="text-xl font-bold">Latest Deck Analysis</h2>
                {analysis ? (
                  <>
                    <div className="mt-5 grid gap-4 sm:grid-cols-3">
                      <div className="rounded-xl bg-slate-50 p-4">
                        <p className="text-xs text-slate-400">Deck ID</p>
                        <p className="mt-2 text-xl font-bold">{analysis.deck.deck_id}</p>
                      </div>
                      <div className="rounded-xl bg-slate-50 p-4">
                        <p className="text-xs text-slate-400">Sections detected</p>
                        <p className="mt-2 text-xl font-bold">{analysis.total_sections}</p>
                      </div>
                      <div className="rounded-xl bg-slate-50 p-4">
                        <p className="text-xs text-slate-400">Text chunks</p>
                        <p className="mt-2 text-xl font-bold">{analysis.total_chunks}</p>
                      </div>
                    </div>

                    <div className="mt-6">
                      <h3 className="mb-3 font-semibold">Extracted Sections</h3>
                      <div className="flex flex-wrap gap-2">
                        {analysis.sections.map((section) => (
                          <span
                            key={section}
                            className="rounded-full bg-indigo-50 px-3 py-2 text-sm text-indigo-700"
                          >
                            {section}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div className="mt-8 space-y-4">
                      <h3 className="font-semibold">Extracted Pitch Deck Content</h3>
                      {analysis.chunks.map((chunk, index) => (
                        <div
                          key={`${chunk.section}-${chunk.chunk_number}-${index}`}
                          className="rounded-xl border p-4"
                        >
                          <div className="mb-3 flex justify-between">
                            <span className="font-semibold text-indigo-700">
                              {chunk.section}
                            </span>
                            <span className="text-xs text-slate-400">
                              Chunk {chunk.chunk_number ?? index + 1}
                            </span>
                          </div>
                          <p className="whitespace-pre-wrap text-sm leading-7 text-slate-600">
                            {chunk.content}
                          </p>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <p className="mt-5 text-sm text-slate-500">
                    No analysis information is available for this startup.
                  </p>
                )}
              </section>
            </>
          )}

          {activeTab === "Investor Matching" && (
            <>
              <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
                <div>
                  <p className="text-sm font-medium text-indigo-600">
                    AI-POWERED DISCOVERY
                  </p>
                  <h1 className="mt-2 text-3xl font-bold">Investor Matching</h1>
                  <p className="mt-2 text-slate-500">
                    Compare investors using your startup and pitch deck data.
                  </p>
                </div>
                <button
                  onClick={generateMatches}
                  disabled={matching || loading}
                  className="rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white disabled:opacity-50"
                >
                  {matching ? "Generating..." : "Generate New Matches"}
                </button>
              </div>

              <div className="mb-6 rounded-2xl border bg-white p-6 shadow-sm">
                <p className="text-sm text-slate-500">Startup ID</p>
                <input
                  value={startupId}
                  onChange={(e) => setStartupId(e.target.value)}
                  type="number"
                  min="1"
                  className="mt-2 w-32 rounded-lg border px-3 py-2 font-bold"
                />
                <button
                  onClick={loadDashboard}
                  className="ml-3 rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white"
                >
                  Load
                </button>
              </div>

              <div className="mb-6 grid gap-5 sm:grid-cols-2">
                <div className="rounded-2xl border bg-white p-6 shadow-sm">
                  <p className="text-sm text-slate-500">Investors Matched</p>
                  <p className="mt-2 text-3xl font-bold text-indigo-600">{matches.length}</p>
                </div>
                <div className="rounded-2xl border bg-white p-6 shadow-sm">
                  <p className="text-sm text-slate-500">Top Match</p>
                  <p className="mt-2 text-xl font-bold">
                    {matches[0]?.investor_name || "No results"}
                  </p>
                  <p className="mt-1 text-sm text-indigo-600">
                    {matches[0] ? score(matches[0].match_score) : ""}
                  </p>
                </div>
              </div>

              {matches.length === 0 ? (
                <div className="rounded-2xl border bg-white py-16 text-center shadow-sm">
                  <p className="text-4xl">🔍</p>
                  <h2 className="mt-4 text-lg font-bold">No saved matching results</h2>
                  <p className="mt-2 text-sm text-slate-500">
                    Generate matches to find compatible investors.
                  </p>
                  <button
                    onClick={generateMatches}
                    disabled={matching}
                    className="mt-5 rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white"
                  >
                    {matching ? "Generating..." : "Generate Matches"}
                  </button>
                </div>
              ) : (
                <div className="space-y-5">
                  {matches.map((investor, index) => (
                    <section
                      key={investor.match_id}
                      className="rounded-2xl border bg-white p-6 shadow-sm"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-4">
                        <div>
                          <h2 className="text-lg font-bold">
                            #{index + 1} {investor.investor_name}
                          </h2>
                          <p className="text-sm text-slate-500">
                            {investor.organization}
                          </p>
                          <p className="mt-1 text-xs text-slate-400">
                            {investor.investor_type}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-3xl font-bold text-indigo-600">
                            {score(investor.match_score)}
                          </p>
                          <p className="text-xs text-slate-400">
                            Compatibility score
                          </p>
                        </div>
                      </div>

                      <div className="mt-5 h-3 overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="h-full rounded-full bg-indigo-600"
                          style={{
                            width: `${Math.min(100, Math.max(0, Number(investor.match_score)))}%`,
                          }}
                        />
                      </div>

                      <div className="mt-6">
                        <h3 className="mb-3 text-sm font-semibold">
                          Compatibility Breakdown
                        </h3>
                        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                          {[
                            ["Industry", investor.industry_score],
                            ["Stage", investor.stage_score],
                            ["Investment", investor.investment_score],
                            ["Location", investor.location_score],
                            ["Similarity", investor.similarity_score],
                          ].map(([label, value]) => (
                            <div key={String(label)} className="rounded-xl bg-slate-50 p-3">
                              <p className="text-xs text-slate-400">{label}</p>
                              <p className="mt-2 font-bold">
                                {score(value as number | null)}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>

                      <p className="mt-4 text-xs text-slate-400">
                        Match generated:{" "}
                        {new Date(investor.generated_at).toLocaleString()}
                      </p>
                    </section>
                  ))}
                </div>
              )}
            </>
          )}

          <footer className="mt-10 border-t border-slate-200 py-6 text-center text-xs text-slate-400">
            StartupMatch · AI-Powered Pitch Deck Analyzer and Investor Matchmaker
          </footer>
        </div>
      </main>
    </div>
  );
}
