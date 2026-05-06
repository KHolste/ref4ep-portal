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
    required: true,
    minlength: "5",
    rows: "3",
    placeholder: "Was hat sich geändert? (mind. 5 Zeichen)",
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
      formData.append("change_note", noteInput.value);
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
    h("label", {}, "Änderungsnotiz (Pflicht)", noteInput),
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
  const wpCode = doc.workpackage.code;

  const admin = isAdmin(me);
  const memberHere = isWpMember(me, wpCode) || admin;
  const leadHere = isWpLead(me, wpCode) || admin;
  const versions = doc.versions || [];

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
    h(
      "p",
      {},
      "Workpackage: ",
      h("a", { href: `/portal/workpackages/${wpCode}` }, wpCode),
      ` — ${doc.workpackage.title}`,
    ),
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

  container.replaceChildren(
    header,
    visibilityNotice || h("div", {}),
    actionsBar || h("div", {}),
    versionsBlock,
    dialogContainer,
    crossNav(),
  );
}
