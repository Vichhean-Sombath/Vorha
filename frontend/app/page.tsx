"use client";

import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { AudioLines, ArrowDownUp, ArrowLeft, ArrowRight, Check, ChevronDown, ChevronRight, Disc3, Heart, History, Home, Library, Link2, ListMusic, LoaderCircle, LogIn, LogOut, MoreHorizontal, Music2, Pause, Play, Plus, RefreshCw, Repeat2, Search, Shuffle, SkipBack, SkipForward, Sparkles, Volume2, X } from "lucide-react";
import type { HistoryItem, Playlist, Sound, User } from "@/types";
import { authApi } from "@/lib/api/auth";
import { favoritesApi } from "@/lib/api/favorites";
import { historyApi } from "@/lib/api/history";
import { playlistsApi } from "@/lib/api/playlists";
import { ApiError, resolveMediaUrl } from "@/lib/api/client";
import { soundsApi } from "@/lib/api/sounds";

const urlSchema = z.string().url("Enter a valid URL.").refine((value) => {
  try { const parsed = new URL(value); return parsed.protocol === "https:" && !parsed.username && !parsed.password && ["tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"].includes(parsed.hostname) && (!parsed.port || parsed.port === "443"); } catch { return false; }
}, "That link doesn’t look like a TikTok video.");

type Section = "discover" | "library" | "history" | "playlists";
type AuthMode = "login" | "register";

function Cover({ sound, className = "" }: { sound?: Sound | null; className?: string }) {
  return <div className={`cover ${className}`}>{sound?.thumbnail_url ? <img src={sound.thumbnail_url} alt="" /> : <AudioLines size={26} strokeWidth={1.5} />}</div>;
}

function BrandMark() {
  return <span className="brand-mark" aria-hidden="true"><Music2 className="brand-mark-note" size={18} strokeWidth={2.3} /><span className="brand-mark-wave"><i /><i /><i /><i /></span></span>;
}

function PlaylistCover({ playlist, className = "" }: { playlist: Playlist; className?: string }) {
  const initials = playlist.name.trim().split(/\s+/).slice(0, 2).map((word) => word[0]).join("").toUpperCase() || "V";
  let hash = 0;
  for (const character of playlist.name) hash = (hash * 31 + character.charCodeAt(0)) | 0;
  const style = [`#111 0%,#444 55%,#888 100%`, `#333 0%,#666 52%,#aaa 100%`, `#555 0%,#888 55%,#ccc 100%`, `#222 0%,#555 50%,#999 100%`][Math.abs(hash) % 4];
  return <div className={`playlist-art ${className}`} style={playlist.cover_image ? undefined : { background: `linear-gradient(145deg,${style})` }} aria-label={`${playlist.name} cover`}>
    {playlist.cover_image ? <img src={playlist.cover_image} alt="" /> : <span>{initials}</span>}
  </div>;
}

async function encodePlaylistImage(file: File): Promise<string> {
  if (!file.type.startsWith("image/")) throw new Error("Choose an image file for the playlist cover.");
  if (file.size > 20 * 1024 * 1024) throw new Error("Choose an image smaller than 20 MB.");
  const bitmap = await createImageBitmap(file);
  const canvas = document.createElement("canvas");
  canvas.width = 640;
  canvas.height = 640;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("This browser can’t prepare that image.");
  const side = Math.min(bitmap.width, bitmap.height);
  context.drawImage(bitmap, (bitmap.width - side) / 2, (bitmap.height - side) / 2, side, side, 0, 0, 640, 640);
  bitmap.close();
  for (const quality of [0.86, 0.76, 0.66, 0.56]) {
    const data = canvas.toDataURL("image/jpeg", quality);
    if (data.length < 860_000) return data;
  }
  throw new Error("That image is too detailed to use. Choose a smaller image.");
}

function formatTime(seconds: number) {
  if (!Number.isFinite(seconds)) return "0:00";
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

function AuthDialog({ mode, onClose, onSuccess }: { mode: AuthMode; onClose: () => void; onSuccess: (user: User) => void }) {
  const [currentMode, setCurrentMode] = useState(mode);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [username, setUsername] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(""); setLoading(true);
    try {
      const result = currentMode === "register"
        ? await authApi.register({ username: username.trim(), email: email.trim(), password })
        : await authApi.login({ email: email.trim(), password });
      onSuccess(result.user);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Couldn’t sign in right now."); }
    finally { setLoading(false); }
  }

  return <div className="auth-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="auth-card">
      <div className="auth-head"><a className="brand" style={{ padding: 0 }}><span className="brand-mark"><AudioLines size={18} /></span><span className="brand-word">Vorha</span></a><button className="button-ghost" aria-label="Close" onClick={onClose}><X size={18} /></button></div>
      <h2>{currentMode === "register" ? "Make room for good sounds." : "Welcome back."}</h2>
      <p className="auth-sub">{currentMode === "register" ? "Create an account to build your personal sound library." : "Sign in to pick up where your listening left off."}</p>
      <form onSubmit={submit}>
        {currentMode === "register" && <><label className="field-label" htmlFor="username">Username</label><input className="field-input" id="username" autoComplete="username" minLength={3} maxLength={50} required value={username} onChange={(event) => setUsername(event.target.value)} placeholder="yourname" /></>}
        <label className="field-label" htmlFor="email">Email</label><input className="field-input" id="email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" />
        <label className="field-label" htmlFor="password">Password</label><input className="field-input" id="password" type="password" autoComplete={currentMode === "register" ? "new-password" : "current-password"} minLength={currentMode === "register" ? 10 : 1} required value={password} onChange={(event) => setPassword(event.target.value)} placeholder={currentMode === "register" ? "At least 10 characters" : "Your password"} />
        {error && <p className="form-error">{error}</p>}
        <button className="button-primary" style={{ width: "100%", marginTop: 20 }} disabled={loading}>{loading ? <LoaderCircle className="spin" size={16} /> : <LogIn size={15} />}{currentMode === "register" ? "Create account" : "Sign in"}</button>
      </form>
      <p className="auth-footer">{currentMode === "register" ? "Already have an account?" : "New to Vorha?"} <button onClick={() => { setError(""); setCurrentMode(currentMode === "register" ? "login" : "register"); }}>{currentMode === "register" ? "Sign in" : "Create an account"}</button></p>
    </div>
  </div>;
}

function PlayerBar({ sound, queue, favorite, playRequest, onFavorite, onSelect, onNext, onPrevious }: { sound: Sound | null; queue: Sound[]; favorite: boolean; playRequest: number; onFavorite: () => void; onSelect: (sound: Sound) => void; onNext: (shuffle?: boolean) => void; onPrevious: () => void }) {
  const mediaRef = useRef<HTMLMediaElement>(null);
  const autoplayNext = useRef(false);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [playerError, setPlayerError] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(0.75);
  const [shuffle, setShuffle] = useState(false);
  const [repeat, setRepeat] = useState(false);
  const [queueOpen, setQueueOpen] = useState(false);
  const handledPlayRequest = useRef(0);
  const available = Boolean(sound?.is_playable && sound.playback_url);
  const source = available ? resolveMediaUrl(sound?.playback_url) ?? undefined : undefined;

  useEffect(() => {
    setPlaying(false); setTime(0); setDuration(sound?.duration_seconds ?? 0); setPlayerError(false); setLoading(Boolean(sound?.is_playable && sound.playback_url));
    if (mediaRef.current) {
      mediaRef.current.load();
      if (playRequest > handledPlayRequest.current && sound?.is_playable && sound.playback_url) {
        handledPlayRequest.current = playRequest;
        setLoading(true);
        void mediaRef.current.play().then(() => { setPlaying(true); setPlayerError(false); }).catch(() => { setPlaying(false); setPlayerError(true); }).finally(() => setLoading(false));
      }
      if (autoplayNext.current && sound?.is_playable && sound.playback_url) {
        autoplayNext.current = false;
        void mediaRef.current.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
      }
    }
  }, [sound?.id, sound?.playback_url, sound?.duration_seconds, playRequest]);
  useEffect(() => { if (mediaRef.current) mediaRef.current.volume = volume; }, [volume]);

  async function toggle() {
    const media = mediaRef.current;
    if (!media || !available) return;
    if (playing) { media.pause(); setPlaying(false); }
    else { setLoading(true); try { await media.play(); setPlaying(true); setPlayerError(false); } catch { setPlaying(false); setPlayerError(true); } finally { setLoading(false); } }
  }

  const handleEnded = () => { setPlaying(false); if (repeat && mediaRef.current) { mediaRef.current.currentTime = 0; void mediaRef.current.play(); setPlaying(true); } else { autoplayNext.current = true; onNext(shuffle); } };
  const handleTimeUpdate = (event: React.SyntheticEvent<HTMLMediaElement>) => setTime(event.currentTarget.currentTime);
  const handleLoadedMetadata = (event: React.SyntheticEvent<HTMLMediaElement>) => setDuration(event.currentTarget.duration || 0);
  const mediaElementProps = { src: source, onTimeUpdate: handleTimeUpdate, onLoadedMetadata: handleLoadedMetadata, onCanPlay: () => setLoading(false), onWaiting: () => setLoading(true), onEnded: handleEnded, onError: () => { setPlaying(false); setLoading(false); setPlayerError(true); }, "aria-hidden": true as const, tabIndex: -1 };

  return <>
    {sound?.playback_media_type === "video" ? <video className="sr-only" ref={(element) => { mediaRef.current = element; }} {...mediaElementProps} playsInline preload="metadata" /> : <audio className="sr-only" ref={(element) => { mediaRef.current = element; }} {...mediaElementProps} preload="metadata" />}
    <div className="player-bar">
      <div className="player-track"><div className="player-cover">{sound?.thumbnail_url ? <img src={sound.thumbnail_url} alt="" /> : <Music2 size={19} />}</div><div className="player-name"><strong>{sound?.title ?? "Your next discovery"}</strong><span>{playerError ? "This audio source could not be played" : loading ? "Loading audio…" : available ? sound?.creator_name ?? "Ready to listen" : sound ? "Audio playback is unavailable" : "Find a sound to start listening"}</span></div><button className="button-ghost desktop-only" aria-label={favorite ? "Remove favorite" : "Add favorite"} onClick={onFavorite}><Heart size={16} fill={favorite ? "currentColor" : "none"} style={{ color: favorite ? "#111111" : undefined }} /></button></div>
      <div className="player-center"><div className="player-controls"><button className={`button-ghost ${shuffle ? "is-on" : ""}`} aria-label="Shuffle" onClick={() => setShuffle(!shuffle)} style={{ color: shuffle ? "#111111" : undefined }}><Shuffle size={15} /></button><button className="button-ghost" aria-label="Previous" onClick={onPrevious}><SkipBack size={17} fill="currentColor" /></button><button className="play-circle" aria-label={playing ? "Pause" : "Play"} disabled={!available || loading} onClick={toggle}>{loading ? <LoaderCircle size={15} className="spin" /> : playing ? <Pause size={16} fill="currentColor" /> : <Play size={16} fill="currentColor" />}</button><button className="button-ghost" aria-label="Next" onClick={() => onNext(false)}><SkipForward size={17} fill="currentColor" /></button><button className="button-ghost" aria-label="Repeat" onClick={() => setRepeat(!repeat)} style={{ color: repeat ? "#111111" : undefined }}><Repeat2 size={15} /></button></div>
        <div className="progress-row"><span>{formatTime(time)}</span><input className="progress-range" type="range" min={0} max={duration || 1} value={Math.min(time, duration || 1)} aria-label="Seek" disabled={!available} onChange={(event) => { if (mediaRef.current) mediaRef.current.currentTime = Number(event.target.value); }} /><span>{duration ? formatTime(duration) : "—:—"}</span></div>
      </div>
      <div className="player-right"><Volume2 size={16} /><input className="volume-range" type="range" min={0} max={1} step={0.01} value={volume} aria-label="Volume" onChange={(event) => setVolume(Number(event.target.value))} /><button className="button-ghost" aria-label="Queue" onClick={() => setQueueOpen(!queueOpen)}><ListMusic size={17} /></button></div>
    </div>
    {queueOpen && <div className="queue-popover"><div className="queue-heading"><strong>Up next</strong><button className="button-ghost" onClick={() => setQueueOpen(false)} aria-label="Close queue"><X size={15} /></button></div>{queue.length ? queue.map((item, index) => <button key={`${item.id}-${index}`} className={`queue-item ${item.id === sound?.id ? "selected" : ""}`} onClick={() => { autoplayNext.current = true; onSelect(item); setQueueOpen(false); }}><Music2 size={14} /><span><strong>{item.title || "Untitled sound"}</strong><small>{item.creator_name || "TikTok creator"}</small></span>{item.id === sound?.id && <span className="queue-playing">Playing</span>}</button>) : <p className="queue-empty">Your queue is empty.</p>}</div>}
    <span className="sr-only">{shuffle ? "Shuffle on" : "Shuffle off"}</span>
  </>;
}

export default function HomePage() {
  const [section, setSection] = useState<Section>("discover");
  const [user, setUser] = useState<User | null>(null);
  const [authMode, setAuthMode] = useState<AuthMode | null>(null);
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Sound | null>(null);
  const [favorites, setFavorites] = useState<Sound[]>([]);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [search, setSearch] = useState("");
  const [librarySounds, setLibrarySounds] = useState<Sound[]>([]);
  const [libraryTotal, setLibraryTotal] = useState(0);
  const [libraryPage, setLibraryPage] = useState(1);
  const [audioError, setAudioError] = useState("");
  const [preparingAudio, setPreparingAudio] = useState(false);
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [activePlaylist, setActivePlaylist] = useState<number | null>(null);
  const [playlistName, setPlaylistName] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [showPlaylistPicker, setShowPlaylistPicker] = useState(false);
  const playlistCoverInput = useRef<HTMLInputElement>(null);
  const [toast, setToast] = useState("");
  const [nowPlaying, setNowPlaying] = useState<Sound | null>(null);
  const [queue, setQueue] = useState<Sound[]>([]);
  const [playRequest, setPlayRequest] = useState(0);

  const active = playlists.find((playlist) => playlist.id === activePlaylist) ?? null;
  const visibleSounds = favoritesOnly ? favorites.filter((sound) => !search.trim() || `${sound.title ?? ""} ${sound.creator_name ?? ""} ${sound.creator_username ?? ""}`.toLowerCase().includes(search.trim().toLowerCase())) : librarySounds;
  useEffect(() => { void authApi.me().then((current) => { setUser(current); void refresh(current); }).catch(() => undefined); }, []);
  useEffect(() => { if (!toast) return; const id = window.setTimeout(() => setToast(""), 3400); return () => window.clearTimeout(id); }, [toast]);
  useEffect(() => {
    if (!user) { setLibrarySounds((items) => items.length ? [] : items); setLibraryTotal((total) => total ? 0 : total); return; }
    let current = true;
    const timer = window.setTimeout(() => {
      void soundsApi.list(search, libraryPage).then((response) => {
        if (!current) return;
        setLibraryTotal(response.total);
        setLibrarySounds((items) => libraryPage === 1 ? response.items : [...items, ...response.items.filter((sound) => !items.some((item) => item.id === sound.id))]);
      }).catch((error) => { if (current) showError(error); });
    }, 220);
    return () => { current = false; window.clearTimeout(timer); };
  }, [user, search, libraryPage, favorites, playlists, history]);

  async function refresh(current = user) {
    if (!current) return;
    const [favs, lists, recent] = await Promise.allSettled([favoritesApi.list(), playlistsApi.list(), historyApi.list()]);
    if (favs.status === "fulfilled") setFavorites(favs.value);
    if (lists.status === "fulfilled") setPlaylists(lists.value);
    if (recent.status === "fulfilled") setHistory(recent.value);
  }

  function showError(error: unknown) {
    if (error instanceof ApiError && error.status === 401) { setAuthMode("login"); return; }
    setToast(error instanceof Error ? error.message : "Something went wrong.");
  }

  async function analyze(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setUrlError("");
    const checked = urlSchema.safeParse(url.trim());
    if (!checked.success) { setUrlError(checked.error.issues[0]?.message ?? "Check the link and try again."); return; }
    setBusy(true); setResult(null);
    try {
      const analyzed = await soundsApi.analyze(checked.data);
      setAudioError("");
      setResult(analyzed.is_playable && analyzed.playback_url ? { ...analyzed, playback_media_type: "audio" } : analyzed);
    }
    catch (error) {
      if (error instanceof ApiError && error.status !== 401) setUrlError(error.message);
      else showError(error);
    }
    finally { setBusy(false); }
  }

  async function retryAudio(sound: Sound) {
    setPreparingAudio(true); setAudioError("");
    try {
      const updated = await soundsApi.prepareAudio(sound.id);
      setResult({ ...updated, playback_media_type: "audio" });
      setToast("Audio is ready to play.");
    } catch (error) {
      setAudioError(error instanceof Error ? error.message : "Could not prepare audio for this video.");
    } finally { setPreparingAudio(false); }
  }

  async function toggleFavorite(sound: Sound) {
    if (!user) { setAuthMode("login"); return; }
    try {
      const saved = favorites.some((item) => item.id === sound.id);
      if (saved) { await favoritesApi.remove(sound.id); setFavorites((items) => items.filter((item) => item.id !== sound.id)); setToast("Removed from favorites"); }
      else { await favoritesApi.add(sound.id); setFavorites((items) => [sound, ...items]); setToast("Saved to favorites"); }
    } catch (error) { showError(error); }
  }

  async function addToPlaylist(playlist: Playlist) {
    if (!result) return;
    try { const updated = await playlistsApi.addSound(playlist.id, result.id); setPlaylists((items) => items.map((item) => item.id === updated.id ? updated : item)); setShowPlaylistPicker(false); setToast(`Added to ${playlist.name}`); }
    catch (error) { showError(error); }
  }

  async function createPlaylist(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!user) { setAuthMode("login"); return; }
    try { const playlist = await playlistsApi.create(playlistName.trim()); setPlaylists((items) => [playlist, ...items]); setActivePlaylist(playlist.id); setSection("playlists"); setPlaylistName(""); setShowCreate(false); setToast("Playlist created"); }
    catch (error) { showError(error); }
  }

  async function changePlaylistCover(file: File) {
    if (!active) return;
    try {
      const cover_image = await encodePlaylistImage(file);
      const updated = await playlistsApi.update(active.id, { cover_image });
      setPlaylists((items) => items.map((item) => item.id === updated.id ? updated : item));
      setToast("Playlist cover updated");
    } catch (error) { showError(error); }
  }

  async function resetPlaylistCover() {
    if (!active) return;
    try {
      const updated = await playlistsApi.update(active.id, { cover_image: null });
      setPlaylists((items) => items.map((item) => item.id === updated.id ? updated : item));
      setToast("Using the title cover");
    } catch (error) { showError(error); }
  }

  async function deletePlaylist(id: number) {
    if (!window.confirm("Delete this playlist? Its saved sounds will remain in your library.")) return;
    try { await playlistsApi.remove(id); setPlaylists((items) => items.filter((item) => item.id !== id)); setActivePlaylist(null); setToast("Playlist deleted"); }
    catch (error) { showError(error); }
  }

  async function removeFromPlaylist(playlistId: number, soundId: number) {
    try { await playlistsApi.removeSound(playlistId, soundId); const updated = await playlistsApi.list(); setPlaylists(updated); setToast("Removed from playlist"); }
    catch (error) { showError(error); }
  }

  async function signOut() { try { await authApi.logout(); } finally { setUser(null); setFavorites([]); setPlaylists([]); setHistory([]); setLibrarySounds([]); setLibraryTotal(0); setSection("discover"); setToast("You’re signed out"); } }

  async function getPlayableSound(sound: Sound): Promise<Sound | null> {
    return sound.is_playable && sound.playback_url ? sound : null;
  }

  async function startQueue(items: Sound[]) {
    const playable = (await Promise.all(items.map(getPlayableSound))).filter((item): item is Sound => Boolean(item));
    setQueue(playable);
    const first = playable[0];
    if (!first) { setToast(items.length ? "No sounds in this playlist have audio ready yet." : "This playlist has no sounds to play yet."); return; }
    setNowPlaying(first);
    setPlayRequest((request) => request + 1);
    if (user) { try { await historyApi.record(first.id); void refresh(); } catch { /* Playback does not depend on history. */ } }
  }

  function goQueue(direction: 1 | -1, random = false) {
    if (!queue.length || !nowPlaying) return;
    if (random && queue.length > 1) {
      const candidates = queue.filter((item) => item.id !== nowPlaying.id);
      setNowPlaying(candidates[Math.floor(Math.random() * candidates.length)]);
      return;
    }
    const index = queue.findIndex((item) => item.id === nowPlaying.id);
    const next = queue[index + direction];
    if (next) setNowPlaying(next);
  }

  const nav = [
    { id: "discover" as const, label: "Discover", icon: Home },
    { id: "library" as const, label: "My library", icon: Library },
    { id: "playlists" as const, label: "Playlists", icon: ListMusic },
  ];

  function navigation() { return nav.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-item ${section === id ? "active" : ""}`} onClick={() => { setSection(id); setActivePlaylist(null); if (id === "library") setFavoritesOnly(false); }}><Icon size={17} /><span>{label}</span>{id === "playlists" && playlists.length > 0 && <span className="nav-count">{playlists.length}</span>}</button>); }

  function openHistory() { setSection("history"); setFavoritesOnly(false); setActivePlaylist(null); }

  function playOne(sound: Sound, items: Sound[]) {
    function beginPlayback(playableSound: Sound) {
      const playableQueue = items.filter((item) => item.is_playable && item.playback_url);
      setQueue(playableQueue.length ? playableQueue : [playableSound]);
      setNowPlaying(playableSound);
      setPlayRequest((request) => request + 1);
      if (user) void historyApi.record(sound.id).then(() => refresh()).catch(() => undefined);
    }
    if (sound.is_playable && sound.playback_url) { beginPlayback(sound); return; }
    void getPlayableSound(sound).then((playableSound) => {
      if (playableSound) beginPlayback(playableSound);
      else setToast("Audio isn’t ready for this sound. Open it in Discover and retry, or attach a local file.");
    });
  }

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#"><BrandMark /><span className="brand-copy"><span className="brand-word">Vorha</span><span className="brand-note">Your sound space</span></span></a>
      <div className="nav-label">Workspace</div>{navigation()}
      <div className="sidebar-bottom">
        <div className="nav-label">Your space</div>
        <button className="nav-item" onClick={() => { if (!user) setAuthMode("login"); else { setSection("library"); setFavoritesOnly(true); setActivePlaylist(null); } }}><Heart size={17} /><span>Favorites</span></button>
        <button className={`nav-item ${section === "history" ? "active" : ""}`} onClick={openHistory}><History size={17} /><span>Recently played</span>{history.length > 0 && <span style={{ marginLeft: "auto", fontSize: 10, opacity: .7 }}>{history.length}</span>}</button>
        <div className="sidebar-note"><div style={{ display: "flex", alignItems: "center", gap: 7, color: "#111111", fontSize: 11, fontWeight: 700 }}><ChevronRight size={14} /> Audio-only playback</div><p>Paste a TikTok link and Vorha plays its soundtrack in the background, with the picture hidden.</p></div>
        {user && <button className="nav-item sidebar-signout" onClick={() => void signOut()}><LogOut size={17} /><span>Sign out</span></button>}
      </div>
    </aside>
    <main className="main-area">
      <header className="topbar">
        <div className="mobile-brand"><BrandMark /><span className="brand-copy"><span className="brand-word">Vorha</span><span className="brand-note">Your sound space</span></span></div>
        <div className="topbar-left"><span>My space</span><ArrowRight size={13} /><strong>{section === "discover" ? "Discover" : section === "library" ? "My library" : section === "history" ? "Recently played" : active?.name ?? "Playlists"}</strong></div>
        <div className="topbar-actions">{user ? <><span style={{ color: "#777383", fontSize: 11 }}>Good to see you, {user.username}</span><span className="avatar">{user.username.slice(0, 1).toUpperCase()}</span></> : <button className="button-secondary" onClick={() => setAuthMode("login")}><LogIn size={14} /> Sign in</button>}</div>
      </header>

      <div className="page-content">
        {section === "discover" && <>
          <div className="eyebrow"><span className="eyebrow-dot" /> A home for sounds you find</div>
          <h1 className="hero-title font-display">Find the sound.<br /><span>Save the moment.</span></h1>
          <p className="hero-subtitle">Paste a TikTok video link and hear its sound right here — audio only, with the picture hidden. Keep the moments that stay with you.</p>

          <form className="search-panel" onSubmit={analyze} noValidate>
            <label className="search-label" htmlFor="tiktok-url">Drop in a TikTok video link</label>
            <div className="search-row"><Link2 className="icon" size={17} /><input id="tiktok-url" type="url" inputMode="url" autoComplete="url" placeholder="https://www.tiktok.com/@creator/video/..." value={url} onChange={(event) => { setUrl(event.target.value); if (urlError) setUrlError(""); }} aria-invalid={Boolean(urlError)} aria-describedby={urlError ? "url-error" : undefined} /><button className="button-primary" type="submit" disabled={busy}>{busy ? <><LoaderCircle size={15} className="spin" /> Preparing audio…</> : <><Sparkles size={15} /> Find sound</>}
</button></div>
            {urlError && <div className="form-error" id="url-error" role="alert">{urlError}</div>}
          </form>

          {result && <section className="result-card" aria-live="polite">
            <Cover sound={result} />
            <div className="sound-main"><div className="sound-topline"><Disc3 size={14} /> Sound details</div><h2 className="sound-title">{result.title || "Untitled sound"}</h2><p className="sound-subtitle">Video by {result.creator_name || (result.creator_username ? `@${result.creator_username}` : "TikTok creator")}</p>
              <div className="sound-meta"><span><Music2 size={12} style={{ verticalAlign: "-2px", marginRight: 5 }} />TikTok video</span><a href={result.source_url} target="_blank" rel="noreferrer" style={{ color: "#777383", textDecoration: "none" }}>Open original <ArrowRight size={11} style={{ verticalAlign: "-1px" }} /></a></div>
              <div className={`sound-actions ${result.is_playable ? "is-playable" : "is-unavailable"}`}><button className="button-primary" disabled={!result.is_playable || !result.playback_url} title={!result.is_playable || !result.playback_url ? "Audio is not ready for this video yet." : "Listen"} onClick={() => void playOne(result, [result])}><Play size={14} fill="currentColor" /> Listen</button>{!result.is_playable && <button className="button-secondary" onClick={() => void retryAudio(result)} disabled={preparingAudio}>{preparingAudio ? <LoaderCircle size={14} className="spin" /> : <RefreshCw size={14} />} {preparingAudio ? "Preparing…" : "Retry audio"}</button>}<button className="button-secondary" onClick={() => void toggleFavorite(result)}><Heart size={14} fill={favorites.some((item) => item.id === result.id) ? "currentColor" : "none"} /> {favorites.some((item) => item.id === result.id) ? "Saved" : "Favorite"}</button><button className="button-secondary" onClick={() => user ? setShowPlaylistPicker(true) : setAuthMode("login")}><Plus size={15} /> Add to playlist</button></div>
              {audioError && <div className="form-error" role="alert">{audioError}</div>}
              {!result.is_playable && <div className="status-chip" style={{ marginTop: 13, width: "fit-content" }}><span style={{ width: 5, height: 5, borderRadius: "50%", background: "#666666" }} /> Audio could not be prepared for this video. Retry to prepare it.</div>}
              {result.is_playable && <div className="status-chip" style={{ marginTop: 13, width: "fit-content" }}><span style={{ width: 5, height: 5, borderRadius: "50%", background: "#666666" }} /> Audio is ready to play in the background.</div>}
            </div>
          </section>}

          {user && <><div className="section-heading"><div><h2 className="section-title">Recently played</h2><p className="section-desc">Pick up where a sound left off.</p></div><button className="text-link" onClick={openHistory}>View listening history <ArrowRight size={12} style={{ verticalAlign: "-2px" }} /></button></div>
            {history.length ? <div className="sound-grid recent-grid">{history.slice(0, 3).map((item) => <SoundCard key={item.sound.id} sound={item.sound} compact onPlay={() => void playOne(item.sound, history.map((entry) => entry.sound))} onFavorite={() => void toggleFavorite(item.sound)} favorite={favorites.some((sound) => sound.id === item.sound.id)} />)}</div> : <div className="empty-state"><div className="empty-icon"><History size={21} /></div><h3>Your listening trail starts here</h3><p>Sounds you play will find a home here, ready when you want them again.</p></div>}
          </>}
        </>}

        {section === "library" && <>
          <div className="eyebrow"><span className="eyebrow-dot" /> Your collection</div><div className="section-heading" style={{ marginTop: 13 }}><div><h1 className="hero-title font-display" style={{ fontSize: 34, margin: 0 }}>{favoritesOnly ? "Favorites" : "My library"}</h1><p className="section-desc" style={{ marginTop: 9 }}>Everything you’ve saved or listened to.</p></div><span className="status-chip">{favoritesOnly ? favorites.length : libraryTotal} {favoritesOnly ? favorites.length === 1 ? "sound" : "sounds" : libraryTotal === 1 ? "sound" : "sounds"}</span></div>
          {user && <div className="library-search"><Search size={15} color="#777383" /><input placeholder="Search titles and creators" value={search} onChange={(event) => { setSearch(event.target.value); setLibraryPage(1); }} /></div>}
          {!user ? <div className="empty-state"><div className="empty-icon"><Library size={21} /></div><h3>Your library is yours to shape</h3><p>Sign in to save favorite sounds, build playlists, and find them later.</p><button className="button-primary" style={{ marginTop: 17 }} onClick={() => setAuthMode("login")}>Sign in</button></div> : visibleSounds.length ? <><div className="sound-grid library-grid">{visibleSounds.map((sound) => <SoundCard key={sound.id} sound={sound} compact onPlay={() => void playOne(sound, visibleSounds)} onFavorite={() => void toggleFavorite(sound)} favorite={favorites.some((item) => item.id === sound.id)} />)}</div>{!favoritesOnly && librarySounds.length < libraryTotal && <div style={{ textAlign: "center", marginTop: 22 }}><button className="button-secondary" onClick={() => setLibraryPage((page) => page + 1)}>Load more sounds</button></div>}</> : <div className="empty-state"><div className="empty-icon"><Music2 size={21} /></div><h3>{favoritesOnly ? "No favorites yet" : "No sounds saved yet"}</h3><p>Find a sound you love and save it here. Your personal library will be waiting.</p><button className="button-secondary" style={{ marginTop: 17 }} onClick={() => { setSection("discover"); setFavoritesOnly(false); }}>Find a sound <ArrowRight size={13} /></button></div>}
        </>}

        {section === "history" && <>
          <div className="eyebrow"><span className="eyebrow-dot" /> Your listening trail</div>
          <div className="section-heading history-heading"><div><h1 className="hero-title font-display" style={{ fontSize: 34, margin: 0 }}>Recently played</h1><p className="section-desc" style={{ marginTop: 9 }}>Pick up where a sound left off.</p></div><span className="status-chip">{history.length} {history.length === 1 ? "play" : "plays"}</span></div>
          {!user ? <div className="empty-state"><div className="empty-icon"><History size={21} /></div><h3>Your listening history lives here</h3><p>Sign in to see the sounds you’ve played and return to them anytime.</p><button className="button-primary" style={{ marginTop: 17 }} onClick={() => setAuthMode("login")}>Sign in</button></div> : history.length ? <div className="history-list">{history.map((item, index) => {
            const sound = item.sound;
            const isPlayable = Boolean(sound.is_playable && sound.playback_url);
            const playedAt = new Date(item.last_played_at);
            const dateLabel = Number.isNaN(playedAt.getTime()) ? "Recently" : playedAt.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
            return <article className="history-row" key={`${sound.id}-${item.last_played_at}`}>
              <span className="history-index">{String(index + 1).padStart(2, "0")}</span>
              <Cover sound={sound} className="history-cover" />
              <div className="history-copy"><h2>{sound.title || "Untitled sound"}</h2><p>{sound.creator_name || "TikTok creator"}</p><span>{dateLabel}</span></div>
              <span className={`history-status ${isPlayable ? "ready" : ""}`}><span />{isPlayable ? "Ready" : "Unavailable"}</span>
              <button className="button-ghost history-favorite" aria-label={favorites.some((saved) => saved.id === sound.id) ? "Remove favorite" : "Add favorite"} onClick={() => void toggleFavorite(sound)}><Heart size={16} fill={favorites.some((saved) => saved.id === sound.id) ? "currentColor" : "none"} style={{ color: favorites.some((saved) => saved.id === sound.id) ? "#111111" : undefined }} /></button>
              <button className="button-ghost history-play" aria-label={isPlayable ? `Play ${sound.title || "sound"}` : "Audio unavailable"} disabled={!isPlayable} onClick={() => void playOne(sound, history.map((entry) => entry.sound))}><Play size={15} fill="currentColor" /></button>
            </article>;
          })}</div> : <div className="empty-state"><div className="empty-icon"><History size={21} /></div><h3>No plays yet</h3><p>Play a sound from Discover or your library and it will appear here.</p><button className="button-secondary" style={{ marginTop: 17 }} onClick={() => setSection("discover")}>Discover sounds <ArrowRight size={13} /></button></div>}
        </>}

        {section === "playlists" && <>
          <div className="eyebrow"><span className="eyebrow-dot" /> Curated by you</div>
          <div className="section-heading" style={{ marginTop: 15 }}><div><h1 className="hero-title font-display" style={{ fontSize: 34, margin: 0 }}>{active?.name ?? "Your playlists"}</h1><p className="section-desc" style={{ marginTop: 9 }}>{active ? active.description || `${active.items.length} sounds collected here.` : "Little collections for the moments that matter."}</p></div>{active ? <div style={{ display: "flex", gap: 7 }}><button className="button-secondary" onClick={() => void startQueue(active.items.map((item) => item.sound))}><Play size={13} fill="currentColor" /> Play playlist</button><button className="button-ghost" aria-label="Back to playlists" onClick={() => setActivePlaylist(null)}><ArrowLeft size={16} /></button></div> : <button className="button-primary" onClick={() => user ? setShowCreate(true) : setAuthMode("login")}><Plus size={15} /> New playlist</button>}</div>
          {!user ? <div className="empty-state"><div className="empty-icon"><ListMusic size={21} /></div><h3>Build a soundtrack for your life</h3><p>Sign in to make playlists and gather your favorite discoveries.</p><button className="button-primary" style={{ marginTop: 17 }} onClick={() => setAuthMode("login")}>Sign in</button></div> : active ? <div className="playlist-detail"><div className="detail-title"><PlaylistCover playlist={active} /><div className="playlist-detail-info"><h3>{active.name}</h3><p>{active.items.length} sounds · Created {new Date(active.created_at).toLocaleDateString()}</p><span className="playlist-cover-hint">{active.cover_image ? "Custom cover" : "Default cover based on title"}</span><div className="playlist-cover-actions"><button className="button-secondary" onClick={() => playlistCoverInput.current?.click()}>Change image</button>{active.cover_image && <button className="button-ghost" onClick={() => void resetPlaylistCover()}>Use title default</button>}<input ref={playlistCoverInput} className="sr-only" type="file" accept="image/*" aria-label="Choose playlist cover image" onChange={(event) => { const file = event.target.files?.[0]; if (file) void changePlaylistCover(file); event.currentTarget.value = ""; }} /></div></div><div style={{ marginLeft: "auto", display: "flex", gap: 4 }}><button className="button-ghost" aria-label="Rename playlist" onClick={async () => { const name = window.prompt("Playlist name", active.name)?.trim(); if (!name || name === active.name) return; try { const updated = await playlistsApi.rename(active.id, name); setPlaylists((items) => items.map((item) => item.id === updated.id ? updated : item)); } catch (error) { showError(error); } }}><MoreHorizontal size={17} /></button><button className="button-ghost" aria-label="Delete playlist" onClick={() => void deletePlaylist(active.id)}><X size={16} /></button></div></div>
            {active.items.length ? active.items.map(({ sound, position }) => <div key={sound.id} className="list-row"><span style={{ width: 19, color: "#777b89", fontSize: 10 }}>{String(position + 1).padStart(2, "0")}</span><Cover sound={sound} /><div className="song-copy"><strong>{sound.title || "Untitled sound"}</strong><span>{sound.creator_name || "TikTok creator"} · {sound.is_playable ? "Ready to play" : "Playback unavailable"}</span></div><button className="button-ghost" aria-label="Move sound up" disabled={position === 0} onClick={async () => { const ids = active.items.map((item) => item.sound.id); [ids[position - 1], ids[position]] = [ids[position], ids[position - 1]]; try { const updated = await playlistsApi.reorder(active.id, ids); setPlaylists((items) => items.map((item) => item.id === updated.id ? updated : item)); } catch (error) { showError(error); } }}><ArrowDownUp size={14} /></button><button className="button-ghost" aria-label="Remove sound" onClick={() => void removeFromPlaylist(active.id, sound.id)}><X size={14} /></button></div>) : <div className="empty-state" style={{ marginTop: 10 }}><div className="empty-icon"><Music2 size={21} /></div><h3>A little room for a new favorite</h3><p>This playlist is empty. Find something you love and add it here.</p><button className="button-secondary" style={{ marginTop: 15 }} onClick={() => setSection("discover")}>Discover sounds</button></div>}
            </div> : playlists.length ? <div className="playlist-list">{playlists.map((playlist) => <div key={playlist.id} role="button" tabIndex={0} className="playlist-row" style={{ textAlign: "left", color: "inherit" }} onClick={() => setActivePlaylist(playlist.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setActivePlaylist(playlist.id); }}><PlaylistCover playlist={playlist} /><div className="playlist-copy"><h3>{playlist.name}</h3><p>{playlist.items.length} sounds{playlist.description ? ` · ${playlist.description}` : ""}</p></div><button className="button-ghost" aria-label={`Play ${playlist.name}`} onClick={(event) => { event.stopPropagation(); void startQueue(playlist.items.map((item) => item.sound)); }}><Play size={15} fill="currentColor" /></button><ChevronDown size={16} style={{ transform: "rotate(-90deg)", color: "#737785" }} /></div>)}</div> : <div className="empty-state"><div className="empty-icon"><ListMusic size={21} /></div><h3>Make your first playlist</h3><p>Collect the sounds you keep coming back to. Every mood can have its own little corner.</p><button className="button-primary" style={{ marginTop: 17 }} onClick={() => setShowCreate(true)}><Plus size={14} /> Create a playlist</button></div>}
        </>}
      </div>
    </main>

    <nav className="bottom-nav">{navigation()}<button className={`nav-item ${section === "history" ? "active" : ""}`} onClick={openHistory}><History size={17} /><span>Recent</span></button></nav>
    <PlayerBar sound={nowPlaying} queue={queue} favorite={Boolean(nowPlaying && favorites.some((item) => item.id === nowPlaying.id))} playRequest={playRequest} onFavorite={() => { if (nowPlaying) void toggleFavorite(nowPlaying); }} onSelect={setNowPlaying} onNext={(random) => goQueue(1, random)} onPrevious={() => goQueue(-1)} />
    {toast && <div className="toast" role="status">{toast}</div>}
    {authMode && <AuthDialog mode={authMode} onClose={() => setAuthMode(null)} onSuccess={(current) => { setUser(current); setAuthMode(null); setToast("You’re all set. Welcome to Vorha."); void refresh(current); }} />}
    {showCreate && <div className="auth-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowCreate(false); }}><div className="auth-card"><div className="auth-head"><span className="eyebrow"><span className="eyebrow-dot" /> New collection</span><button className="button-ghost" onClick={() => setShowCreate(false)} aria-label="Close"><X size={17} /></button></div><h2>Name this feeling.</h2><p className="auth-sub">Give your new playlist a name you’ll remember.</p><form onSubmit={createPlaylist}><label className="field-label" htmlFor="playlist-name">Playlist name</label><input className="field-input" id="playlist-name" autoFocus maxLength={100} required value={playlistName} onChange={(event) => setPlaylistName(event.target.value)} placeholder="Late night loops" /><button className="button-primary" style={{ width: "100%", marginTop: 19 }}><Plus size={15} /> Create playlist</button></form></div></div>}
    {showPlaylistPicker && <div className="auth-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowPlaylistPicker(false); }}><div className="auth-card"><div className="auth-head"><span className="eyebrow"><span className="eyebrow-dot" /> Save this sound</span><button className="button-ghost" onClick={() => setShowPlaylistPicker(false)} aria-label="Close"><X size={17} /></button></div><h2>Add to a playlist</h2><p className="auth-sub">Choose a collection for “{result?.title ?? "this sound"}”.</p>{playlists.length ? <div className="playlist-list">{playlists.map((playlist) => <button key={playlist.id} className="playlist-row" onClick={() => void addToPlaylist(playlist)}><PlaylistCover playlist={playlist} /><div className="playlist-copy"><h3>{playlist.name}</h3><p>{playlist.items.length} sounds</p></div><Plus size={16} /></button>)}</div> : <div className="empty-state"><h3>No playlists yet</h3><p>Create one to keep this sound close.</p></div>}<button className="button-secondary" style={{ width: "100%", marginTop: 13 }} onClick={() => { setShowPlaylistPicker(false); setShowCreate(true); }}><Plus size={14} /> Create a playlist</button></div></div>}
  </div>;
}

function SoundCard({ sound, onPlay, onFavorite, favorite, compact = false }: { sound: Sound; onPlay: () => void; onFavorite: () => void; favorite: boolean; compact?: boolean }) {
  const canPlay = Boolean(sound.is_playable && sound.playback_url);
  return <article className={`mini-card ${compact ? "compact-card" : ""}`}><Cover sound={sound} /><h3 className="mini-title">{sound.title || "Untitled sound"}</h3><p className="mini-subtitle">{sound.creator_name || "TikTok creator"}</p><div className="mini-actions">{compact ? <><button className="button-ghost recent-favorite-button" aria-label={favorite ? "Remove favorite" : "Add favorite"} onClick={onFavorite}>{favorite ? "Saved" : "Favorite"}</button><button className="recent-play-button" aria-label={canPlay ? `Play ${sound.title || "sound"}` : "Audio unavailable"} title={canPlay ? "Play" : "Audio unavailable"} disabled={!canPlay} onClick={onPlay}><Play size={15} fill="currentColor" /></button></> : <><button className="button-ghost" aria-label={canPlay ? "Play sound" : "Audio unavailable"} disabled={!canPlay} onClick={onPlay}><Play size={14} fill="currentColor" /></button><span style={{ color: "#737785", fontSize: 9 }}>{canPlay ? "Ready" : "Unavailable"}</span><button className="button-ghost" aria-label={favorite ? "Remove favorite" : "Add favorite"} onClick={onFavorite}>{favorite ? "Saved" : "Favorite"}</button></>}</div></article>;
}
