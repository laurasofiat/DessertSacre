document.addEventListener("DOMContentLoaded", () => {
  /* ══════════════════════════════════════════
     STRIPE
     ══════════════════════════════════════════ */
  const stripe = Stripe(
    "pk_test_51TcY862SCdGx4wuyJrax4QuqOWsw6QBxTD4npRg0brXEva1rCTvp0CL14C3JbcyCEgopY7fRfL1liY8zUebWAtHX00f2rnLByr",
  );
  let elements = null;
  let metodoSeleccionado = "stripe";

  /* ══════════════════════════════════════════
     SELECTOR DE MÉTODO
     ══════════════════════════════════════════ */
  document.querySelectorAll(".metodo").forEach((btn) => {
    btn.addEventListener("click", () => {
      document
        .querySelectorAll(".metodo")
        .forEach((b) => b.classList.remove("activo"));
      btn.classList.add("activo");
      metodoSeleccionado = btn.dataset.metodo;
      mostrarPanel(metodoSeleccionado);
    });
  });

  function mostrarPanel(metodo) {
    ["stripe", "nequi", "efecty"].forEach((m) => {
      const p = document.getElementById("panel-" + m);
      if (p) p.hidden = m !== metodo;
    });
    if (metodo === "stripe") iniciarStripe();
    if (metodo === "nequi") cargarDatosPago("nequi");
    if (metodo === "efecty") cargarDatosPago("efecty");
  }

  /* ══════════════════════════════════════════
     DATOS MANUALES (Nequi / Efecty)
     ══════════════════════════════════════════ */
  function cargarDatosPago(metodo) {
    const div = document.getElementById("info-" + metodo);
    if (!div) return;

    // Si ya cargó, no vuelve a pedir
    if (div.dataset.loaded === "1") return;

    fetch(`/api/datos-pago?metodo=${metodo}`)
      .then((res) => res.json())
      .then((data) => {
        const d = data.datos;
        const total = document.getElementById("total").textContent;
        if (!d) return;

        if (metodo === "nequi") {
          div.innerHTML = `
            <p class="metodo-titulo">📱 Pagar con Nequi</p>
            <div class="metodo-datos">
              <div class="dato-fila"><span>Número</span><strong>${d.numero}</strong></div>
              <div class="dato-fila"><span>Titular</span><strong>${d.titular}</strong></div>
              <div class="dato-fila"><span>Monto</span><strong>${total}</strong></div>
            </div>
            <p class="metodo-nota">Envía el comprobante al WhatsApp <strong>+57 321 458 6088</strong> con el asunto <em>"Pedido Dessert Sacré"</em>.</p>
          `;
        }

        if (metodo === "efecty") {
          div.innerHTML = `
            <p class="metodo-titulo">💵 Pago por Efecty</p>
            <div class="metodo-datos">
              <div class="dato-fila"><span>Convenio</span><strong>${d.convenio}</strong></div>
              <div class="dato-fila"><span>Titular</span><strong>${d.titular}</strong></div>
              <div class="dato-fila"><span>Monto</span><strong>${total}</strong></div>
            </div>
            <p class="metodo-nota">Acércate a cualquier punto Efecty y guarda el recibo.</p>
          `;
        }

        div.dataset.loaded = "1";
      })
      .catch((err) => console.error("Error cargando datos de pago:", err));
  }

  /* ══════════════════════════════════════════
     STRIPE ELEMENTS
     ══════════════════════════════════════════ */
  async function iniciarStripe() {
    if (elements) return;

    const errEl = document.getElementById("payment-errors");
    errEl.textContent = "";

    try {
      const resp = await fetch("/procesar_pago", { method: "POST" });
      const data = await resp.json();

      if (data.error) {
        errEl.textContent = data.error;
        return;
      }

      const appearance = {
        theme: "stripe",
        variables: {
          fontWeightNormal: "500",
          borderRadius: "2px",
          colorPrimary: "#7a3535",
          tabIconSelectedColor: "#fff",
          gridRowSpacing: "16px",
        },
        rules: {
          ".Tab, .Input, .Block, .CheckboxInput, .CodeInput": {
            boxShadow: "0px 3px 10px rgba(18, 42, 66, 0.08)",
          },
          ".Block": { borderColor: "transparent" },
          ".BlockDivider": { backgroundColor: "#ebebeb" },
          ".Tab, .Tab:hover, .Tab:focus": { border: "0" },
          ".Tab--selected, .Tab--selected:hover": {
            backgroundColor: "#7a3535",
            color: "#fff",
          },
        },
      };

      elements = stripe.elements({
        clientSecret: data.clientSecret,
        appearance,
      });
      elements
        .create("payment", {
          layout: { type: "tabs", defaultCollapsed: false },
        })
        .mount("#payment-element");
    } catch (err) {
      document.getElementById("payment-errors").textContent =
        "Error al iniciar el pago: " + err.message;
    }
  }

  /* ── Submit formulario tarjeta ── */
  document
    .getElementById("payment-form")
    .addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!elements) return;

      setBusy(true);

      const { error } = await stripe.confirmPayment({
        elements,
        confirmParams: {
          return_url: window.location.origin + "/pago_exitoso",
          receipt_email: document.getElementById("email").value,
        },
      });

      if (error) {
        document.getElementById("payment-errors").textContent = error.message;
        setBusy(false);
      }
      // Si no hay error, Stripe redirige solo a /pago_exitoso
    });

  /* ══════════════════════════════════════════
     BOTONES MANUALES — Nequi / Efecty
     ══════════════════════════════════════════ */
  ["nequi", "efecty"].forEach((metodo) => {
    const btn = document.getElementById("btn-" + metodo);
    if (!btn) return;

    btn.addEventListener("click", () => {
      const nombre = document.getElementById("nombre").value;
      const email = document.getElementById("email").value;
      const telefono = document.getElementById("telefono").value;

      btn.disabled = true;
      btn.textContent = "Procesando...";

      fetch("/api/crear-pedido", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ metodo, nombre, email, telefono }),
      })
        .then((res) => {
          if (!res.ok)
            return res.json().then((e) => {
              throw new Error(e.error || res.status);
            });
          return res.json();
        })
        .then((data) => {
          mostrarResultado(
            `
          ¡Pedido confirmado!<br>
          Ref: <strong>${data.referencia}</strong><br>
           Total: <strong>$${data.total.toLocaleString("es-CO")}</strong><br>
           Realiza el pago y envía el comprobante.<br>
          <small>Redirigiendo en 3 segundos…</small>
        `,
            "exito",
          );
          setTimeout(() => {
            window.location.href = "/inicioU";
          }, 3000);
        })
        .catch((err) => {
          btn.disabled = false;
          btn.textContent = "Ya realicé el pago";
          mostrarResultado(" Error: " + err.message, "error");
        });
    });
  });

  /* ══════════════════════════════════════════
     HELPERS
     ══════════════════════════════════════════ */
  function setBusy(busy) {
    document.getElementById("btn-text").hidden = busy;
    document.getElementById("spinner").hidden = !busy;
    document.getElementById("btnPagar").disabled = busy;
  }

  function mostrarResultado(html, tipo) {
    const el = document.getElementById("resultado");
    el.innerHTML = html;
    el.className = "show " + tipo;
  }

  mostrarPanel(metodoSeleccionado);
}); // fin DOMContentLoaded
