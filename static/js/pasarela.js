document.addEventListener("DOMContentLoaded", () => {
  const stripe = Stripe(
    "pk_test_51TcY862SCdGx4wuyJrax4QuqOWsw6QBxTD4npRg0brXEva1rCTvp0CL14C3JbcyCEgopY7fRfL1liY8zUebWAtHX00f2rnLByr",
  );

  let elements = null;

  /* ==========================
     CAMBIO DE MÉTODO DE PAGO
  ========================== */

  document.querySelectorAll(".metodo").forEach((btn) => {
    btn.addEventListener("click", () => {
      document
        .querySelectorAll(".metodo")
        .forEach((b) => b.classList.remove("activo"));

      btn.classList.add("activo");

      mostrarPanel(btn.dataset.metodo);
    });
  });

  function mostrarPanel(metodo) {
    document.getElementById("panel-stripe").hidden = true;
    document.getElementById("panel-nequi").hidden = true;
    document.getElementById("panel-daviplata").hidden = true;

    const comprobante = document.getElementById("seccion-comprobante");

    if (comprobante) {
      comprobante.style.display = "none";
    }

    const panel = document.getElementById("panel-" + metodo);

    if (panel) {
      panel.hidden = false;
    }

    if (metodo === "stripe") {
      iniciarStripe();
    }
  }
  /* ==========================
     STRIPE
  ========================== */

  async function iniciarStripe() {
    if (elements) return;

    try {
      const resp = await fetch("/procesar_pago", {
        method: "POST",
      });

      const data = await resp.json();

      if (data.error) {
        document.getElementById("payment-errors").textContent = data.error;
        return;
      }

      elements = stripe.elements({
        clientSecret: data.clientSecret,
      });

      elements
        .create("payment", {
          layout: {
            type: "tabs",
          },
        })
        .mount("#payment-element");
    } catch (err) {
      console.error(err);
    }
  }

  /*Boton stripe*/
  const formPago = document.getElementById("payment-form");

  if (formPago) {
    formPago.addEventListener("submit", async (e) => {
      e.preventDefault();

      const btn = document.getElementById("btnPagar");

      btn.disabled = true;

      const { error } = await stripe.confirmPayment({
        elements,

        confirmParams: {
          return_url: window.location.origin + "/pago_exitoso",
        },
      });

      if (error) {
        document.getElementById("payment-errors").innerHTML = error.message;

        btn.disabled = false;
      }
    });
  }

  /* 
Botones nequi  y daviplata */

  const btnNequi = document.getElementById("btn-nequi");
  const btnDaviplata = document.getElementById("btn-daviplata");
  const seccion = document.getElementById("seccion-comprobante");

  if (btnNequi && seccion) {
    btnNequi.addEventListener("click", () => {
      btnNequi.insertAdjacentElement("afterend", seccion);

      ```
seccion.style.display = "block";

seccion.scrollIntoView({
  behavior: "smooth",
});
```;
    });
  }

  if (btnDaviplata && seccion) {
    btnDaviplata.addEventListener("click", () => {
      btnDaviplata.insertAdjacentElement("afterend", seccion);

      ```
seccion.style.display = "block";

seccion.scrollIntoView({
  behavior: "smooth",
});
```;
    });
  }

  /* ==========================
     COPIAR NÚMERO NEQUI
  ========================== */

  window.copiarNumero = async function (idElemento) {
    const numero = document.getElementById(idElemento).innerText.trim();

    try {
      await navigator.clipboard.writeText(numero);
      alert("Número copiado: " + numero);
    } catch (err) {
      console.error(err);
    }
  };

  /* ==========================
     SUBIR COMPROBANTE
  ========================== */

  window.subirComprobante = async function () {
    const archivo = document.getElementById("input-comprobante").files[0];

    if (!archivo) {
      alert("Selecciona un comprobante.");
      return;
    }

    const formData = new FormData();

    formData.append("comprobante", archivo);

    try {
      const resp = await fetch("/subir-comprobante", {
        method: "POST",
        body: formData,
      });

      const data = await resp.json();

      if (data.ok) {
        document.getElementById("mensaje-comprobante").innerHTML =
          "Comprobante enviado correctamente ";

        // espera un momento y vuelve al inicio
        setTimeout(() => {
          window.location.href = "/inicioU";
        }, 1500);
      } else {
        alert(data.error);
      }
    } catch (err) {
      console.error(err);
      alert("Error enviando comprobante");
    }
  };
  /* ==========================
   BOTÓN DAVIPLATA
========================== */

  if (btnDaviplata) {
    btnDaviplata.addEventListener("click", () => {
      const seccion = document.getElementById("seccion-comprobante");

      if (seccion) {
        seccion.style.display = "block";

        seccion.scrollIntoView({
          behavior: "smooth",
        });
      }
    });
  }

  /* ==========================
     INICIO
  ========================== */

  mostrarPanel("stripe");
});
