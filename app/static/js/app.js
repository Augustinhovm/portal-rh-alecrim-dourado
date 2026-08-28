(() => {
  "use strict";

  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const token = csrfMeta ? csrfMeta.content : "";

  document.querySelectorAll('form').forEach((form) => {
    const method = (form.getAttribute("method") || "get").toLowerCase();
    if (method !== "post") return;
    if (form.querySelector('input[name="_csrf_token"]')) return;

    const field = document.createElement("input");
    field.type = "hidden";
    field.name = "_csrf_token";
    field.value = token;
    form.appendChild(field);
  });

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const message = form.dataset.confirm || "Confirma esta operação?";
      if (!window.confirm(message)) event.preventDefault();
    });
  });

  const body = document.body;
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("sidebarOverlay");
  const toggle = document.getElementById("menuToggle");
  const close = document.getElementById("sidebarClose");

  if (sidebar && overlay && toggle && close) {
    const openMenu = () => {
      body.classList.add("sidebar-open");
      sidebar.setAttribute("aria-hidden", "false");
      toggle.setAttribute("aria-expanded", "true");
    };

    const closeMenu = () => {
      body.classList.remove("sidebar-open");
      sidebar.setAttribute("aria-hidden", "true");
      toggle.setAttribute("aria-expanded", "false");
    };

    toggle.addEventListener("click", () => {
      if (body.classList.contains("sidebar-open")) closeMenu();
      else openMenu();
    });
    close.addEventListener("click", closeMenu);
    overlay.addEventListener("click", closeMenu);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeMenu();
    });
    sidebar.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));
  }

  const clock = document.getElementById("clock");
  if (clock) {
    const updateClock = () => {
      clock.textContent = new Date().toLocaleTimeString("pt-BR", {
        timeZone: "America/Sao_Paulo"
      });
    };
    updateClock();
    window.setInterval(updateClock, 500);
  }
})();