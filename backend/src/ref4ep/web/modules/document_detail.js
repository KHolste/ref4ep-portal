import { api, h } from "/portal/common.js";

const TYPE_LABELS = {
  deliverable: "Deliverable",
  report: "Report",
  note: "Notiz",
  other: "Sonstiges",
};

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MiB`;
}

function renderVersionsTable(documentId, versions) {
  if (!versions.length) {
    return h(
      "p",
      { class: "muted" },
      "Noch keine Version hochgeladen — füg die erste über »Neue Version hochladen« hinzu.",
    );
  }
  const rows = versions
    .slice()
    .reverse()
    .map((v) =>
      h(
        "tr",
        {},
        h("td", {}, `v${v.version_number}`),
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
            {
              href: `/api/documents/${documentId}/versions/${v.version_number}/download`,
            },
            "Download",
          ),
        ),
      ),
    );
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
  const fileInput = h("input", { type: "file", name: "file", required: true });
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
    h("label", {}, "Datei", fileInput),
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
      h("option", { value: t, selected: t === document_.document_type ? true : null }, TYPE_LABELS[t]),
    ),
  );
  const codeInput = h("input", { type: "text", value: document_.deliverable_code || "" });
  const errorBox = h("p", { class: "error", style: "display:none" }, "");

  async function onSubmit(ev) {
    ev.preventDefault();
    errorBox.style.display = "none";
    try {
      const updated = await api("PATCH", `/api/documents/${document_.id}`, {
        title: titleInput.value,
        document_type: typeSelect.value,
        deliverable_code: codeInput.value || null,
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
    h("label", {}, "Deliverable-Code", codeInput),
    errorBox,
    h("button", { type: "submit" }, "Speichern"),
  );
}

export async function render(container, ctx) {
  const documentId = ctx.params.id;
  const doc = await api("GET", `/api/documents/${documentId}`);

  const header = h(
    "div",
    {},
    h("h1", {}, doc.title),
    h(
      "p",
      {},
      "Workpackage: ",
      h("a", { href: `/portal/workpackages/${doc.workpackage.code}` }, doc.workpackage.code),
      ` — ${doc.workpackage.title}`,
    ),
    h(
      "p",
      {},
      `Typ: ${TYPE_LABELS[doc.document_type] || doc.document_type}`,
      doc.deliverable_code ? ` · Deliverable-Code: ${doc.deliverable_code}` : "",
    ),
    h(
      "p",
      {},
      `Status: ${doc.status} · Sichtbarkeit: ${doc.visibility}`,
    ),
    h("p", { class: "muted" }, `Angelegt von ${doc.created_by.display_name}`),
  );

  const dialogContainer = h("div", {});

  function showUpload() {
    dialogContainer.replaceChildren(
      h(
        "div",
        { class: "dialog" },
        h("h3", {}, "Neue Version hochladen"),
        renderUploadDialog(documentId, () => {
          ctx.navigate(`/portal/documents/${documentId}`); // reload via dispatcher
          window.location.reload();
        }),
      ),
    );
  }

  function showMetadataEdit() {
    dialogContainer.replaceChildren(
      h(
        "div",
        { class: "dialog" },
        h("h3", {}, "Metadaten bearbeiten"),
        renderMetadataDialog(doc, () => {
          window.location.reload();
        }),
      ),
    );
  }

  const actions = h(
    "div",
    { class: "actions" },
    h("button", { type: "button", onclick: showUpload }, "Neue Version hochladen"),
    h("button", { type: "button", onclick: showMetadataEdit }, "Metadaten bearbeiten"),
  );

  const versionsBlock = h(
    "section",
    {},
    h("h2", {}, "Versionen"),
    renderVersionsTable(documentId, doc.versions || []),
  );

  container.replaceChildren(header, actions, versionsBlock, dialogContainer);
}
