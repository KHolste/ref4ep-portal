import {
  api,
  createFileDropzone,
  crossNav,
  h,
  pageHeader,
  renderEmpty,
  renderError,
  renderLoading,
} from "/portal/common.js";

const TYPE_LABELS = {
  deliverable: "Deliverable",
  report: "Report",
  note: "Notiz",
  paper: "Paper",
  other: "Sonstiges",
};

const STATUS_BADGES = {
  draft: { label: "Entwurf", cls: "badge badge-draft" },
  in_review: { label: "Review", cls: "badge badge-review" },
  released: { label: "Freigegeben", cls: "badge badge-released" },
};

const VISIBILITY_BADGES = {
  workpackage: { label: "WP-intern", cls: "badge badge-wp" },
  internal: { label: "Konsortium", cls: "badge badge-internal" },
  public: { label: "Öffentlich", cls: "badge badge-public" },
};

// Beschriftungen für die 9 Link-Labels der Junction
// ``test_campaign_document_link`` (siehe domain/models.py, identisch zu
// ``DOC_LABEL_LABELS`` in campaign_detail.js).
const DOC_LABEL_LABELS = {
  test_plan: "Messplan",
  setup_plan: "Aufbauplan",
  safety_document: "Sicherheitsunterlage",
  raw_data_description: "Rohdatenbeschreibung",
  protocol: "Protokoll",
  analysis: "Auswertung",
  presentation: "Präsentation",
  attachment: "Anlage",
  other: "Sonstiges",
};

const CAMPAIGN_STATUS_LABELS = {
  planned: "geplant",
  preparing: "Vorbereitung",
  running: "läuft",
  completed: "abgeschlossen",
  evaluated: "ausgewertet",
  cancelled: "abgebrochen",
  postponed: "verschoben",
};

// Block 0024 — Lebenszyklus eines Review-Kommentars.
const DOCUMENT_COMMENT_STATUS_LABELS = {
  open: "offen",
  submitted: "eingereicht",
};

// Block 0035 — Bibliotheksbereich-Labels für Dokumente ohne WP-Bezug.
const LIBRARY_SECTION_LABELS = {
  project: "Projektunterlagen",
  milestone: "Meilenstein-Dokumente",
  literature: "Literatur & Veröffentlichungen",
  presentation: "Vorträge",
  thesis: "Abschlussarbeiten",
};

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MiB`;
}

function isAdmin(me) {
  return me?.person?.platform_role === "admin";
}

function isWpLead(me, wpCode) {
  return (me?.memberships || []).some(
    (m) => m.workpackage_code === wpCode && m.wp_role === "wp_lead",
  );
}

function isWpMember(me, wpCode) {
  return (me?.memberships || []).some((m) => m.workpackage_code === wpCode);
}

function badge(spec) {
  return h("span", { class: spec.cls }, spec.label);
}

function renderVersionsTable(documentId, versions, releasedVersionId) {
  if (!versions.length) {
    return renderEmpty(
      "Noch keine Version hochgeladen — füg die erste über »Neue Version hochladen« hinzu.",
    );
  }
  const rows = versions
    .slice()
    .reverse()
    .map((v) => {
      const isReleased = v.id === releasedVersionId;
      return h(
        "tr",
        { class: isReleased ? "row-released" : "" },
        h("td", {}, isReleased ? `★ v${v.version_number}` : `v${v.version_number}`),
        h("td", {}, v.version_label || ""),
        h("td", {}, v.change_note),
        h("td", {}, v.original_filename),
        h("td", {}, formatBytes(v.file_size_bytes)),
        h("td", { title: v.sha256 }, `${v.sha256.slice(0, 10)}…`),
        h("td", {}, v.uploaded_by.display_name),
        h("td", {}, new Date(v.uploaded_at).toLocaleString("de-DE")),
        h(
          "td",
          {},
          h(
            "a",
            { href: `/api/documents/${documentId}/versions/${v.version_number}/download` },
            "Download",
          ),
        ),
      );
    });
  return h(
    "table",
    {},
    h(
      "thead",
      {},
      h(
        "tr",
        {},
        h("th", {}, "#"),
        h("th", {}, "Label"),
        h("th", {}, "Änderungsnotiz"),
        h("th", {}, "Datei"),
        h("th", {}, "Größe"),
        h("th", {}, "SHA-256"),
        h("th", {}, "Hochladende"),
        h("th", {}, "Datum"),
        h("th", {}, ""),
      ),
    ),
    h("tbody", {}, ...rows),
  );
}

function renderUploadDialog(documentId, onSuccess) {
  // Klassisches Datei-Auswahlfeld bleibt erhalten (Tastatur-/A11y-Pfad);
  // ``createFileDropzone`` legt eine zusätzliche Drag-and-Drop-Zone
  // drumherum. Submit liest weiterhin ``fileInput.files[0]``.
  const fileInput = h("input", { type: "file", name: "file", required: true });
  const fileDropzone = createFileDropzone({
    input: fileInput,
    ariaLabel: "Datei für neue Version",
  });
  const noteInput = h("textarea", {
    name: "change_note",
    rows: "3",
    placeholder: "Was hat sich geändert? (optional)",
  });
  const labelInput = h("input", { type: "text", name: "version_label" });
  const errorBox = h("p", { class: "error", style: "display:none" }, "");
  const statusBox = h("p", { class: "muted", style: "display:none" }, "Lade hoch …");
  const submitBtn = h("button", { type: "submit" }, "Hochladen");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    if (!fileInput.files.length) {
      errorBox.textContent = "Bitte eine Datei wählen.";
      errorBox.style.display = "";
      return;
    }
    submitBtn.disabled = true;
    statusBox.style.display = "";
    try {
      const formData = new FormData();
      formData.append("file", fileInput.files[0]);
      // Block 0036: nur senden, wenn der Nutzer wirklich etwas
      // eingegeben hat — sonst greift der Server-Default
      // (``Initialer Upload`` / ``Neue Version hochgeladen``).
      const noteValue = (noteInput.value || "").trim();
      if (noteValue) formData.append("change_note", noteValue);
      if (labelInput.value) formData.append("version_label", labelInput.value);

      const csrf = (document.cookie.match(/(?:^|;\s*)ref4ep_csrf=([^;]+)/) || [])[1];
      const response = await fetch(`/api/documents/${documentId}/versions`, {
        method: "POST",
        body: formData,
        credentials: "same-origin",
        headers: csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {},
      });
      if (response.status === 401) {
        window.location.href = "/login";
        return;
      }
      const payload = await response.json().catch(() => null);
      if (!response.ok) {
        const message = payload?.detail?.error?.message || `HTTP ${response.status}`;
        throw new Error(message);
      }
      onSuccess(payload);
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    } finally {
      submitBtn.disabled = false;
      statusBox.style.display = "none";
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit, enctype: "multipart/form-data" },
    h("label", {}, "Datei", fileDropzone),
    h("label", {}, "Änderungsnotiz (optional)", noteInput),
    h("label", {}, "Versions-Label (optional)", labelInput),
    statusBox,
    errorBox,
    submitBtn,
  );
}

function renderMetadataDialog(document_, onSaved) {
  const titleInput = h("input", { type: "text", value: document_.title, required: true });
  const typeSelect = h(
    "select",
    {},
    ...["deliverable", "report", "note", "other"].map((t) =>
      h(
        "option",
        { value: t, selected: t === document_.document_type ? true : null },
        TYPE_LABELS[t],
      ),
    ),
  );
  const codeInput = h("input", {
    type: "text",
    value: document_.deliverable_code || "",
    placeholder: "z. B. D1.1",
  });
  const codeHelp = h(
    "small",
    { class: "field-hint" },
    "Optional — z. B. „D1.1“ oder „REF4EP-WP1-001“. Leer lassen für „kein Code“.",
  );
  const descriptionInput = h(
    "textarea",
    { rows: "3", placeholder: "Kurze inhaltliche Beschreibung (optional)" },
    document_.description || "",
  );
  const descriptionHelp = h(
    "small",
    { class: "field-hint" },
    "Optional. Erscheint im Dokument-Detail; nicht in der öffentlichen Bibliothek.",
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      const updated = await api("PATCH", `/api/documents/${document_.id}`, {
        title: titleInput.value,
        document_type: typeSelect.value,
        deliverable_code: codeInput.value || null,
        description: descriptionInput.value || null,
      });
      onSaved(updated);
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Titel", titleInput),
    h("label", {}, "Typ", typeSelect),
    h("label", {}, "Dokumentcode / Deliverable-Code (optional)", codeInput, codeHelp),
    h("label", {}, "Beschreibung (optional)", descriptionInput, descriptionHelp),
    errorBox,
    h("button", { type: "submit" }, "Speichern"),
  );
}

function renderReleaseDialog(documentId, versions, defaultVersion, onSuccess) {
  const select = h(
    "select",
    {},
    ...versions
      .slice()
      .reverse()
      .map((v) =>
        h(
          "option",
          { value: String(v.version_number), selected: v.version_number === defaultVersion ? true : null },
          `v${v.version_number} — ${v.original_filename}`,
        ),
      ),
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api("POST", `/api/documents/${documentId}/release`, {
        version_number: parseInt(select.value, 10),
      });
      onSuccess();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Version freigeben", select),
    errorBox,
    h("button", { type: "submit" }, "Freigeben"),
  );
}

function renderVisibilityDialog(documentId, current, canPublic, onSuccess) {
  const options = [
    { value: "workpackage", label: "WP-intern (nur WP-Mitglieder)" },
    { value: "internal", label: "Konsortium (alle Eingeloggten)" },
  ];
  if (canPublic) {
    options.push({ value: "public", label: "Öffentlich (extern sichtbar nach Release)" });
  }
  const select = h(
    "select",
    {},
    ...options.map((o) =>
      h("option", { value: o.value, selected: o.value === current ? true : null }, o.label),
    ),
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api("POST", `/api/documents/${documentId}/visibility`, { to: select.value });
      onSuccess();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Sichtbarkeit", select),
    errorBox,
    h("button", { type: "submit" }, "Übernehmen"),
  );
}

// ---- Kommentare (Block 0024) ---------------------------------------------

// Spiegelung der Backend-Logik ``can_comment_document``:
// - Released-Doc: jedes Konsortiumsmitglied (eingeloggt).
// - Sonst: Admin oder WP-Mitglied.
function canCommentDocument(me, doc) {
  if (!me?.person) return false;
  if (doc.is_deleted) return false;
  if (isAdmin(me)) return true;
  if (doc.status === "released") return true;
  // Block 0035: Dokumente ohne WP-Bezug haben keinen
  // Mitgliedschafts-Pfad — Kommentieren ist dann Admin/released-only.
  if (!doc.workpackage) return false;
  return isWpMember(me, doc.workpackage?.code);
}

function isOwnComment(me, comment) {
  return me?.person?.email === comment.author.email;
}

function fmtDateTime(isoString) {
  if (!isoString) return "";
  return new Date(isoString).toLocaleString("de-DE");
}

function renderAddCommentBox(versionId, onSaved) {
  const textArea = h("textarea", {
    rows: "3",
    placeholder: "Neuer Kommentar (wird zunächst privat als „offen“ gespeichert)",
    required: true,
    minlength: "1",
  });
  const errorBox = h("p", { class: "error", style: "display:none" }, "");
  const submitBtn = h("button", { type: "submit" }, "Kommentar speichern");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const cleaned = textArea.value.trim();
    if (!cleaned) {
      errorBox.textContent = "Bitte Text eingeben.";
      errorBox.style.display = "";
      return;
    }
    submitBtn.disabled = true;
    try {
      await api(
        "POST",
        `/api/document-versions/${versionId}/comments`,
        { text: cleaned },
      );
      onSaved();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    } finally {
      submitBtn.disabled = false;
    }
  }

  return h(
    "form",
    { class: "stacked comment-add-form", onsubmit: onSubmit },
    h("label", {}, "Neuer Kommentar", textArea),
    errorBox,
    submitBtn,
  );
}

function renderEditCommentForm(comment, onSaved, onCancel) {
  const textArea = h("textarea", { rows: "3", required: true }, comment.text);
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const cleaned = textArea.value.trim();
    if (!cleaned) {
      errorBox.textContent = "Bitte Text eingeben.";
      errorBox.style.display = "";
      return;
    }
    try {
      await api("PATCH", `/api/document-comments/${comment.id}`, { text: cleaned });
      onSaved();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  return h(
    "form",
    { class: "stacked comment-edit-form", onsubmit: onSubmit },
    textArea,
    errorBox,
    h(
      "div",
      { class: "actions" },
      h("button", { type: "submit" }, "Übernehmen"),
      h("button", { type: "button", onclick: onCancel }, "Abbrechen"),
    ),
  );
}

function renderCommentItem(comment, me, onChanged) {
  const own = isOwnComment(me, comment);
  const admin = isAdmin(me);
  const statusBadge = h(
    "span",
    { class: `badge badge-comment-${comment.status}` },
    DOCUMENT_COMMENT_STATUS_LABELS[comment.status] || comment.status,
  );

  const meta = h(
    "p",
    { class: "muted" },
    `${comment.author.display_name} · ${fmtDateTime(comment.created_at)}`,
    comment.submitted_at
      ? ` · eingereicht ${fmtDateTime(comment.submitted_at)}`
      : "",
  );

  const body = h("p", { class: "comment-text" }, comment.text);
  const container = h("article", { class: "comment-item" });

  function rerender() {
    container.replaceChildren(
      h("div", { class: "comment-header" }, statusBadge, " ", meta),
      body,
    );
    const actions = [];
    if (own && comment.status === "open") {
      actions.push(
        h(
          "button",
          {
            type: "button",
            onclick: () => {
              container.replaceChildren(
                h("div", { class: "comment-header" }, statusBadge, " ", meta),
                renderEditCommentForm(comment, onChanged, rerender),
              );
            },
          },
          "Bearbeiten",
        ),
        h(
          "button",
          {
            type: "button",
            onclick: async () => {
              if (!confirm("Kommentar einreichen? Danach unveränderlich.")) return;
              try {
                await api("POST", `/api/document-comments/${comment.id}/submit`, {});
                onChanged();
              } catch (err) {
                alert(err.message);
              }
            },
          },
          "Einreichen",
        ),
      );
    }
    if (admin) {
      actions.push(
        h(
          "button",
          {
            type: "button",
            class: "danger",
            onclick: async () => {
              if (!confirm("Kommentar wirklich löschen? Audit-Log hält die Aktion fest.")) return;
              try {
                await api("DELETE", `/api/document-comments/${comment.id}`);
                onChanged();
              } catch (err) {
                alert(err.message);
              }
            },
          },
          "Löschen",
        ),
      );
    }
    if (actions.length) {
      container.appendChild(h("div", { class: "actions" }, ...actions));
    }
  }

  rerender();
  return container;
}

function renderCommentsSection(doc, me, versions, commentsByVersion, onChanged) {
  const canComment = canCommentDocument(me, doc);
  if (!versions.length) {
    return h(
      "section",
      {},
      h("h2", {}, "Kommentare"),
      renderEmpty("Kommentare sind erst möglich, wenn eine Version hochgeladen wurde."),
    );
  }
  const blocks = versions
    .slice()
    .reverse()
    .map((v) => {
      const list = commentsByVersion.get(v.id) || [];
      const heading = h(
        "h3",
        {},
        `v${v.version_number}`,
        v.version_label ? ` — ${v.version_label}` : "",
        h("span", { class: "muted" }, ` · ${list.length} Kommentar(e)`),
      );
      const items = list.length
        ? list.map((c) => renderCommentItem(c, me, onChanged))
        : [renderEmpty("Noch keine Kommentare zu dieser Version.")];
      const children = [heading, ...items];
      if (canComment) {
        children.push(renderAddCommentBox(v.id, onChanged));
      }
      return h("div", { class: "comments-version-block" }, ...children);
    });
  return h("section", {}, h("h2", {}, "Kommentare"), ...blocks);
}

function renderTestCampaignsSection(doc, canEdit, openLinkDialog, onUnlinked) {
  const links = doc.test_campaigns || [];
  const headerActions = canEdit
    ? h(
        "button",
        { type: "button", onclick: openLinkDialog },
        "Testkampagne verknüpfen …",
      )
    : null;
  const body = links.length
    ? h(
        "table",
        {},
        h(
          "thead",
          {},
          h(
            "tr",
            {},
            h("th", {}, "Code"),
            h("th", {}, "Titel"),
            h("th", {}, "Status"),
            h("th", {}, "Rolle im Dokument"),
            canEdit ? h("th", {}, "") : null,
          ),
        ),
        h(
          "tbody",
          {},
          ...links.map((link) =>
            h(
              "tr",
              {},
              h(
                "td",
                {},
                h(
                  "a",
                  { href: `/portal/campaigns/${link.id}` },
                  link.code,
                ),
              ),
              h("td", {}, link.title),
              h(
                "td",
                {},
                CAMPAIGN_STATUS_LABELS[link.status] || link.status,
              ),
              h(
                "td",
                {},
                DOC_LABEL_LABELS[link.label] || link.label,
              ),
              canEdit
                ? h(
                    "td",
                    {},
                    h(
                      "button",
                      {
                        type: "button",
                        class: "danger",
                        onclick: () => onUnlinked(link),
                      },
                      "Entfernen",
                    ),
                  )
                : null,
            ),
          ),
        ),
      )
    : renderEmpty("Keine Testkampagne zugeordnet.");
  return h(
    "section",
    {},
    h(
      "div",
      { class: "section-header" },
      h("h2", {}, "Testkampagnen"),
      headerActions,
    ),
    body,
  );
}

function renderLinkCampaignDialog(documentId, wpCode, onSaved) {
  const campaignSelect = h("select", {}, h("option", { value: "" }, "— wird geladen —"));
  const labelSelect = h(
    "select",
    {},
    ...Object.entries(DOC_LABEL_LABELS).map(([v, l]) =>
      h(
        "option",
        { value: v, ...(v === "test_plan" ? { selected: "" } : {}) },
        l,
      ),
    ),
  );
  const errorBox = h("p", { class: "error", style: "display:none" }, "");
  const submitBtn = h("button", { type: "submit", disabled: "" }, "Verknüpfen");
  const emptyHint = h("p", { class: "muted", style: "display:none" }, "");

  // Kampagnen für dieses Workpackage asynchron laden.
  api("GET", `/api/campaigns?workpackage=${encodeURIComponent(wpCode)}`)
    .then((items) => {
      campaignSelect.replaceChildren();
      if (!items || items.length === 0) {
        campaignSelect.append(
          h("option", { value: "" }, "— keine Kampagne in diesem WP —"),
        );
        emptyHint.textContent =
          "Es existiert noch keine Testkampagne, die zu diesem Workpackage gehört.";
        emptyHint.style.display = "";
        return;
      }
      for (const c of items) {
        campaignSelect.append(
          h(
            "option",
            { value: c.id },
            `${c.code} — ${c.title}`,
          ),
        );
      }
      submitBtn.disabled = false;
    })
    .catch((err) => {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    });

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    const campaignId = campaignSelect.value;
    if (!campaignId) {
      errorBox.textContent = "Bitte eine Kampagne auswählen.";
      errorBox.style.display = "";
      return;
    }
    try {
      await api("POST", `/api/documents/${documentId}/test-campaigns`, {
        campaign_id: campaignId,
        label: labelSelect.value,
      });
      onSaved();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }

  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h("label", {}, "Kampagne", campaignSelect),
    h("label", {}, "Rolle des Dokuments", labelSelect),
    emptyHint,
    errorBox,
    submitBtn,
  );
}

function renderDeleteConfirm(documentId, onSuccess) {
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      await api("DELETE", `/api/documents/${documentId}`);
      onSuccess();
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.style.display = "";
    }
  }
  return h(
    "form",
    { class: "stacked", onsubmit: onSubmit },
    h(
      "p",
      {},
      "Soft-Delete: Das Dokument wird ausgeblendet, aber " +
        "Versionen und Storage-Dateien bleiben physisch erhalten.",
    ),
    errorBox,
    h("button", { type: "submit" }, "Soft-Delete bestätigen"),
  );
}

export async function render(container, ctx) {
  container.classList.add("page-wide");
  const documentId = ctx.params.id;
  const me = ctx.me;
  container.replaceChildren(
    pageHeader("Dokument"),
    renderLoading("Dokument wird geladen …"),
  );
  let doc;
  try {
    doc = await api("GET", `/api/documents/${documentId}`);
  } catch (err) {
    container.replaceChildren(pageHeader("Dokument"), renderError(err));
    return;
  }
  // Block 0035: ``doc.workpackage`` darf null sein
  // (Projektbibliothek-Dokumente ohne WP-Bezug). Alle WP-bezogenen
  // Zugriffe sind null-safe; Admin-Pfad bleibt als Fallback wirksam.
  const wpCode = doc.workpackage?.code ?? null;

  const admin = isAdmin(me);
  const memberHere = wpCode ? isWpMember(me, wpCode) || admin : admin;
  const leadHere = wpCode ? isWpLead(me, wpCode) || admin : admin;
  const versions = doc.versions || [];

  // WP- bzw. Bibliotheks-Zeile: bei WP-Bezug der bekannte Link auf
  // das Arbeitspaket, sonst eine sachliche Anzeige des Bibliotheks-
  // bereichs bzw. „ohne Arbeitspaketbezug".
  let scopeLine;
  if (doc.workpackage) {
    scopeLine = h(
      "p",
      {},
      "Workpackage: ",
      h("a", { href: `/portal/workpackages/${wpCode}` }, wpCode),
      ` — ${doc.workpackage?.title}`,
    );
  } else {
    const sectionLabel = doc.library_section
      ? LIBRARY_SECTION_LABELS[doc.library_section] || doc.library_section
      : null;
    scopeLine = h(
      "p",
      {},
      "Projektbibliothek",
      sectionLabel ? ` · Bereich: ${sectionLabel}` : "",
      " · ohne Arbeitspaketbezug",
    );
  }

  const header = h(
    "div",
    {},
    h(
      "h1",
      {},
      doc.title,
      " ",
      badge(STATUS_BADGES[doc.status] || STATUS_BADGES.draft),
      " ",
      badge(VISIBILITY_BADGES[doc.visibility] || VISIBILITY_BADGES.workpackage),
    ),
    scopeLine,
    h(
      "p",
      {},
      `Typ: ${TYPE_LABELS[doc.document_type] || doc.document_type}`,
      doc.deliverable_code ? ` · Dokumentcode: ${doc.deliverable_code}` : "",
    ),
    doc.description ? h("p", { class: "doc-description" }, doc.description) : null,
    h("p", { class: "muted" }, `Angelegt von ${doc.created_by.display_name}`),
  );

  // Hinweisbanner bei visibility=public und status≠released.
  const visibilityNotice =
    doc.visibility === "public" && doc.status !== "released"
      ? h(
          "p",
          { class: "warning" },
          "Sichtbarkeit ist öffentlich, das Dokument ist aber noch nicht freigegeben — " +
            "es erscheint erst ab dem Release in der öffentlichen Bibliothek.",
        )
      : null;

  const dialogContainer = h("div", {});

  function reload() {
    window.location.reload();
  }

  function showDialog(title, body) {
    dialogContainer.replaceChildren(h("div", { class: "dialog" }, h("h3", {}, title), body));
  }

  // Aktionsleiste rollenabhängig.
  const actions = [];
  if (memberHere) {
    actions.push(
      h(
        "button",
        {
          type: "button",
          onclick: () =>
            showDialog(
              "Neue Version hochladen",
              renderUploadDialog(documentId, reload),
            ),
        },
        "Neue Version hochladen …",
      ),
      h(
        "button",
        {
          type: "button",
          onclick: () =>
            showDialog(
              "Metadaten bearbeiten",
              renderMetadataDialog(doc, reload),
            ),
        },
        "Metadaten bearbeiten …",
      ),
    );
    if (doc.status === "draft" && versions.length > 0) {
      actions.push(
        h(
          "button",
          {
            type: "button",
            onclick: async () => {
              try {
                await api("POST", `/api/documents/${documentId}/status`, { to: "in_review" });
                reload();
              } catch (err) {
                alert(err.message);
              }
            },
          },
          "Zur Review schicken",
        ),
      );
    }
    if (doc.status === "in_review") {
      actions.push(
        h(
          "button",
          {
            type: "button",
            onclick: async () => {
              try {
                await api("POST", `/api/documents/${documentId}/status`, { to: "draft" });
                reload();
              } catch (err) {
                alert(err.message);
              }
            },
          },
          "Zurück zu Draft",
        ),
      );
    }
  }
  if (leadHere && (doc.status === "in_review" || doc.status === "released") && versions.length > 0) {
    const defaultVer = versions[versions.length - 1].version_number;
    const label =
      doc.status === "released" ? "Andere Version freigeben …" : "Version freigeben …";
    actions.push(
      h(
        "button",
        {
          type: "button",
          onclick: () =>
            showDialog(
              "Version freigeben",
              renderReleaseDialog(documentId, versions, defaultVer, reload),
            ),
        },
        label,
      ),
    );
  }
  if (admin && doc.status === "released") {
    actions.push(
      h(
        "button",
        {
          type: "button",
          onclick: async () => {
            if (!confirm("Freigabe wirklich zurückziehen?")) return;
            try {
              await api("POST", `/api/documents/${documentId}/unrelease`, {});
              reload();
            } catch (err) {
              alert(err.message);
            }
          },
        },
        "Freigabe zurückziehen",
      ),
    );
  }
  if (memberHere) {
    actions.push(
      h(
        "button",
        {
          type: "button",
          onclick: () =>
            showDialog(
              "Sichtbarkeit ändern",
              renderVisibilityDialog(documentId, doc.visibility, leadHere, reload),
            ),
        },
        "Sichtbarkeit ändern …",
      ),
    );
  }
  if (admin) {
    actions.push(
      h(
        "button",
        {
          type: "button",
          class: "danger",
          onclick: () =>
            showDialog(
              "Dokument soft-löschen",
              renderDeleteConfirm(documentId, () => {
                window.location.href = `/portal/workpackages/${wpCode}`;
              }),
            ),
        },
        "Soft-Delete …",
      ),
    );
  }

  const actionsBar = actions.length ? h("div", { class: "actions" }, ...actions) : null;

  const versionsBlock = h(
    "section",
    {},
    h("h2", {}, "Versionen"),
    renderVersionsTable(documentId, versions, doc.released_version_id),
  );

  async function unlinkCampaign(link) {
    if (
      !confirm(
        `Verknüpfung mit Kampagne ${link.code} wirklich entfernen?`,
      )
    )
      return;
    try {
      await api(
        "DELETE",
        `/api/documents/${documentId}/test-campaigns/${link.id}`,
      );
      reload();
    } catch (err) {
      alert(err.message);
    }
  }

  function openLinkCampaignDialog() {
    showDialog(
      "Testkampagne verknüpfen",
      renderLinkCampaignDialog(documentId, wpCode, reload),
    );
  }

  const campaignsBlock = renderTestCampaignsSection(
    doc,
    memberHere,
    openLinkCampaignDialog,
    unlinkCampaign,
  );

  // Comments asynchron pro Version laden — failt eine Version, bleibt
  // die Seite trotzdem rendierbar.
  const commentsByVersion = new Map();
  const commentResults = await Promise.all(
    versions.map(async (v) => {
      try {
        const list = await api("GET", `/api/document-versions/${v.id}/comments`);
        return [v.id, list];
      } catch {
        return [v.id, []];
      }
    }),
  );
  for (const [vid, list] of commentResults) commentsByVersion.set(vid, list);

  const commentsBlock = renderCommentsSection(
    doc,
    me,
    versions,
    commentsByVersion,
    reload,
  );

  container.replaceChildren(
    header,
    visibilityNotice || h("div", {}),
    actionsBar || h("div", {}),
    versionsBlock,
    campaignsBlock,
    commentsBlock,
    dialogContainer,
    crossNav(),
  );
}
