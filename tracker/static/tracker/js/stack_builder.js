(function () {
  const registry = new Map();

  function sanitize(value) {
    if (value === undefined || value === null) {
      return "";
    }
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function assignBuilderId(element) {
    if (!element.dataset.builderId) {
      const uid = `stack-builder-${Math.random().toString(36).slice(2, 9)}`;
      element.dataset.builderId = uid;
    }
    return element.dataset.builderId;
  }

  function updateRemoveState(tbody, minRows) {
    const buttons = tbody.querySelectorAll(".stack-builder-remove");
    const disable = tbody.children.length <= minRows;
    buttons.forEach((btn) => {
      btn.disabled = disable;
      btn.classList.toggle("text-muted", disable);
    });
  }

  function normalizeCategory(value) {
    return (value || "").trim().toLowerCase();
  }

  function enforceUniqueType(input, tbody) {
    // Removed unique type validation - allow duplicate types
    if (!input) return;
    input.dataset.lastValidValue = input.value || "";
    input.classList.remove("is-invalid");
    input.setCustomValidity("");
  }

  function refreshTypeState(tbody) {
    // Removed duplicate clearing logic - preserve all values
    tbody.querySelectorAll(".stack-type-input").forEach((input) => {
      input.dataset.lastValidValue = input.value || "";
      input.classList.remove("is-invalid");
      input.setCustomValidity("");
    });
  }

  function attachTypeInputHandlers(row, tbody) {
    const typeInput = row.querySelector(".stack-type-input");
    if (!typeInput) return;
    typeInput.dataset.lastValidValue = typeInput.value || "";
    typeInput.addEventListener("focus", function () {
      typeInput.dataset.lastValidValue = typeInput.value || "";
    });
    typeInput.addEventListener("change", function () {
      enforceUniqueType(typeInput, tbody);
    });
  }

  function setupBuilder(element) {
    const builderId = assignBuilderId(element);
    const tbody = element.querySelector(".stack-builder-body");
    const addBtn = element.querySelector(".stack-builder-add");
    const datalistId = element.dataset.datalistId || "";
    const minRows = parseInt(element.dataset.minRows || "1", 10);

    if (!tbody) {
      return;
    }

    function createRow(data = {}) {
      const row = document.createElement("tr");
      row.classList.add("stack-builder-row");
      row.innerHTML = `
        <td>
          <input type="text" class="form-control form-control-sm stack-type-input" name="component_type[]" list="${datalistId}"
            placeholder="Select type" value="${sanitize(data.category)}" required />
        </td>
        <td>
          <input type="text" class="form-control form-control-sm" name="component_name[]" placeholder="Component name"
            value="${sanitize(data.name)}" required />
        </td>
        <td>
          <input type="text" class="form-control form-control-sm" name="component_version[]" placeholder="Version"
            value="${sanitize(data.version)}" required />
        </td>
        <td>
          <input type="text" class="form-control form-control-sm" name="component_scope[]" placeholder="Scope / Notes"
            value="${sanitize(data.scope)}" />
        </td>
        <td class="text-center">
          <button type="button" class="btn btn-link text-danger p-0 stack-builder-remove" aria-label="Remove component">
            <i class="bi bi-trash"></i>
          </button>
        </td>
      `;

      const removeBtn = row.querySelector(".stack-builder-remove");
      if (removeBtn) {
        removeBtn.addEventListener("click", function () {
          if (tbody.children.length <= minRows) {
            return;
          }
          row.remove();
          updateRemoveState(tbody, minRows);
          refreshTypeState(tbody);
        });
      }

      return row;
    }

    function addRow(data = {}) {
      const newRow = createRow(data);
      tbody.appendChild(newRow);
      attachTypeInputHandlers(newRow, tbody);
      refreshTypeState(tbody);
      updateRemoveState(tbody, minRows);
    }

    function setRows(rows) {
      tbody.innerHTML = "";
      const payload = Array.isArray(rows) && rows.length ? rows : [];
      if (!payload.length) {
        addRow({});
      } else {
        payload.forEach((rowData) => {
          const newRow = createRow(rowData);
          tbody.appendChild(newRow);
          attachTypeInputHandlers(newRow, tbody);
        });
        refreshTypeState(tbody);
      }
      updateRemoveState(tbody, minRows);
    }

    if (addBtn) {
      addBtn.addEventListener("click", function (event) {
        event.preventDefault();
        addRow({});
      });
    }

    let initialRows = [];
    const initialRaw = element.dataset.initialRows;
    if (initialRaw) {
      try {
        const parsed = JSON.parse(initialRaw);
        if (Array.isArray(parsed)) {
          initialRows = parsed;
        }
      } catch (err) {
        console.warn("Stack builder initialRows parse error:", err);
      }
    }

    setRows(initialRows);

    registry.set(builderId, {
      element,
      tbody,
      setRows,
    });
  }

  function resolveBuilder(target) {
    if (!target) return null;

    if (typeof target === "string") {
      return registry.get(target) || null;
    }

    if (target instanceof HTMLElement) {
      const id = target.dataset.builderId;
      if (id && registry.has(id)) {
        return registry.get(id);
      }
    }

    return null;
  }

  window.LibTrackStack = {
    setRows(target, rows) {
      const builder = resolveBuilder(target);
      if (builder) {
        builder.setRows(rows);
      }
    },
    reset(target) {
      const builder = resolveBuilder(target);
      if (builder) {
        builder.setRows([]);
      }
    },
  };

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".stack-builder").forEach(setupBuilder);
  });
})();
