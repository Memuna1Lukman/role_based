import { useEffect, useState } from "react";
import { api, websocketUrl } from "./api";

function Toasts({ items }) { return <div className="toasts" aria-live="assertive">{items.map((item) => <div className={`toast ${item.tone || "info"}`} key={item.id}>{item.message}</div>)}</div>; }

function Login({ onSignedIn, notify }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(""); const form = new FormData(event.currentTarget);
    try { await api("/auth/login", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ username: form.get("email"), password: form.get("password") }) }); await onSignedIn(); }
    catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  return <main className="auth-shell"><form className="auth-card" onSubmit={submit}><p className="eyebrow">FLOWBOARD</p><h1>Welcome back</h1><p className="muted">Sign in to your project workspace.</p><label>Email<input name="email" type="email" autoComplete="email" required /></label><label>Password<input name="password" type="password" autoComplete="current-password" required /></label>{error && <p className="error" role="alert">{error}</p>}<button disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button></form></main>;
}

function ProjectCard({ project, currentUser, notify }) {
  const [open, setOpen] = useState(false); const [tasks, setTasks] = useState([]); const [membership, setMembership] = useState(null); const [loading, setLoading] = useState(false);
  async function openProject() {
    if (!open) { setLoading(true); try { const [members, fetchedTasks] = await Promise.all([api(`/projects/${project.id}/members`), api(`/projects/${project.id}/tasks`)]); setMembership(members.find((member) => member.user_id === currentUser.id)); setTasks(fetchedTasks); } catch (err) { notify(err.message, "error"); } finally { setLoading(false); } } setOpen(!open);
  }
  const canManage = currentUser.role === "ADMIN" || membership?.role === "PROJECT_LEAD";
  return (
    <article className="project-card">
      <div className="card-top"><div><p className="eyebrow">PROJECT</p><h3>{project.name}</h3></div><button className="quiet" onClick={openProject} aria-expanded={open}>{open ? "Close" : "Open"}</button></div>
      <p className="muted">{project.description || "No description yet."}</p>
      {open && (
        <div className="project-detail">
          {loading ? <p className="muted">Loading work…</p> : (
            <>
              <div className="detail-header"><strong>Tasks</strong>{canManage && <span className="role-chip">Can manage</span>}</div>
              {tasks.length ? <ul className="task-list">{tasks.map((task) => <li key={task.id}><span>{task.title}</span><span className={`status ${task.status.toLowerCase()}`}>{task.status.replace("_", " ")}</span></li>)}</ul> : <p className="muted">No tasks yet.</p>}
              {!canManage && <p className="hint">Members can view work; assigned members can update the status of their assigned task.</p>}
            </>
          )}
        </div>
      )}
    </article>
  );
}

function Workspace({ user, onLogout, notify, realtimeTick }) {
  const [projects, setProjects] = useState([]); const [notifications, setNotifications] = useState([]); const [loading, setLoading] = useState(true);
  async function refresh() { setLoading(true); try { const [projectData, noticeData] = await Promise.all([api("/projects/"), api("/notify?limit=10")]); setProjects(projectData); setNotifications(noticeData); } catch (err) { notify(err.message, "error"); } finally { setLoading(false); } }
  useEffect(() => { refresh(); }, [realtimeTick]);
  const unread = notifications.filter((item) => !item.is_read).length;
  return <div className="shell"><aside className="sidebar"><a className="brand" href="#top">Flowboard</a><nav><a className="active" href="#projects">Projects</a><a href="#notifications">Notifications {unread > 0 && <span className="count">{unread}</span>}</a></nav><div className="profile"><strong>{user.full_name}</strong><span>{user.role.replace("_", " ")}</span><button className="quiet" onClick={onLogout}>Sign out</button></div></aside><main className="content" id="top"><header><div><p className="eyebrow">WORKSPACE</p><h1>Projects</h1><p className="muted">The work that needs your attention.</p></div><button onClick={refresh}>Refresh</button></header><section className="panel" id="projects"><div className="panel-heading"><h2>All projects</h2>{user.role === "ADMIN" && <span className="role-chip">Administrator</span>}</div><div className="project-grid">{loading ? <p className="muted">Loading projects…</p> : projects.length ? projects.map((project) => <ProjectCard key={project.id} project={project} currentUser={user} notify={notify} />) : <div className="empty"><h3>No projects yet</h3><p>Ask an administrator to add you to a project.</p></div>}</div></section><section className="panel" id="notifications"><div className="panel-heading"><h2>Notifications</h2><button className="quiet" onClick={async () => { await api("/notify/read-all", { method: "POST" }); refresh(); }}>Mark all read</button></div>{notifications.length ? notifications.map((item) => <article className={`notice ${item.is_read ? "" : "unread"}`} key={item.id}><div><strong>{item.title}</strong><p>{item.message}</p></div><time>{new Date(item.created_at).toLocaleString()}</time></article>) : <p className="muted">You are all caught up.</p>}</section></main></div>;
}

export default function App() {
  const [user, setUser] = useState(null); const [booting, setBooting] = useState(true); const [toasts, setToasts] = useState([]); const [realtimeTick, setRealtimeTick] = useState(0);
  const notify = (message, tone = "info") => { const id = crypto.randomUUID(); setToasts((current) => [...current, { id, message, tone }]); window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 5000); };
  async function loadUser() { try { await api("/auth/refresh", { method: "POST" }); setUser(await api("/users/me")); } catch { setUser(null); } finally { setBooting(false); } }
  useEffect(() => { loadUser(); }, []);
  useEffect(() => { if (!user) return; const socket = new WebSocket(websocketUrl()); socket.onmessage = ({ data }) => { const event = JSON.parse(data); if (event.type === "notification.created") notify(event.data.title, "success"); if (event.type === "notification.created" || event.type === "project.event") setRealtimeTick((count) => count + 1); }; return () => socket.close(); }, [user]);
  async function logout() { await api("/auth/logout", { method: "POST" }).catch(() => {}); setUser(null); notify("You have been signed out."); }
  if (booting) return <main className="auth-shell"><p className="muted">Loading Flowboard…</p></main>;
  return <><Toasts items={toasts} />{user ? <Workspace user={user} onLogout={logout} notify={notify} realtimeTick={realtimeTick} /> : <Login onSignedIn={loadUser} notify={notify} />}</>;
}
