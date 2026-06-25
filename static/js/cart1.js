/* ══════════════════════════════════════════
   BADGE DEL NAVBAR
══════════════════════════════════════════ */
function cacheCartCount(count) {
  const badge = document.getElementById("cart-count");
  if (badge) badge.textContent = count;
}

/* ══════════════════════════════════════════
   MENSAJES DE ESTADO EN CARRITO
══════════════════════════════════════════ */
function updateCartStatus(message, type = "success") {
  const status = document.getElementById("cart-status");
  if (!status) return;
  status.innerHTML = `
    <div class="alert alert-${type} alert-dismissible fade show" role="alert">
      ${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    </div>`;
}

/* ══════════════════════════════════════════
   CARGAR CANTIDAD DEL CARRITO DESDE EL SERVER
══════════════════════════════════════════ */
async function loadCartCount() {
  try {
    const res = await fetch("/api/cart");
    const data = await res.json();
    cacheCartCount(data.total_items || 0);
  } catch (e) {
    console.error("Error cargando carrito:", e);
  }
}

/* ══════════════════════════════════════════
   AGREGAR PRODUCTO AL CARRITO VÍA API
══════════════════════════════════════════ */
async function addToCartAPI(name, price) {
  try {
    const res = await fetch("/agregar_carrito", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nombre: name, precio: price }),
    });
    const data = await res.json();
    if (data.success) {
      cacheCartCount(data.total_items || 0);
      updateCartStatus(`Se agregó "${name}" al carrito.`, "success");
    } else {
      updateCartStatus(
        data.error || "No se pudo agregar el producto.",
        "danger",
      );
    }
  } catch {
    updateCartStatus("Error de red al agregar el producto.", "danger");
  }
}

function initAddToCartButtons() {
  document.querySelectorAll(".btn-warning.add-to-cart").forEach((button) => {
    button.addEventListener("click", async (e) => {
      e.preventDefault();
      const name = button.dataset.name;
      const price = parseFloat(button.dataset.price);
      if (!name || !price) {
        updateCartStatus(
          "No se pudo leer el nombre o precio del producto.",
          "danger",
        );
        return;
      }
      await addToCartAPI(name, price);
    });
  });
}

/* ══════════════════════════════════════════
   ACTUALIZAR TOTAL EN CARRITO
══════════════════════════════════════════ */
function updateTotalUI(totalPrice, totalItems) {
  const totalEl = document.getElementById("cart-total");
  if (totalEl)
    totalEl.textContent = `COP ${totalPrice.toLocaleString("es-CO", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    })}`;
  cacheCartCount(totalItems);
}

/* ══════════════════════════════════════════
   API CARRITO
══════════════════════════════════════════ */
async function updateQuantity(index, qty) {
  const res = await fetch("/api/cart/update", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index, qty }),
  });
  return res.json();
}

async function removeItem(index) {
  const res = await fetch("/api/cart/remove", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index }),
  });
  return res.json();
}

function reindexCart() {
  document.querySelectorAll("#cart-items tr").forEach((row, i) => {
    row.dataset.index = i;
    const btn = row.querySelector(".remove-item");
    if (btn) btn.dataset.index = i;
    const input = row.querySelector(".qty-input");
    if (input) input.name = `qty_${i}`;
  });
}

/* ══════════════════════════════════════════
   TABLA DEL CARRITO
══════════════════════════════════════════ */
function initCartTable() {
  document.querySelectorAll(".qty-input").forEach((input) => {
    input.addEventListener("change", async () => {
      const row = input.closest("tr");
      const index = Number(row.dataset.index);
      const qty = parseInt(input.value);
      if (isNaN(index) || isNaN(qty) || qty < 1) return;

      const result = await updateQuantity(index, qty);
      if (result.success) {
        updateTotalUI(result.total_price, result.total_items);
        const precioTexto = row.children[1].textContent
          .replace("COP", "")
          .replace(/\./g, "")
          .replace(/,/g, "")
          .trim();
        const precio = parseFloat(precioTexto);
        row.children[3].textContent = `COP ${(precio * qty).toLocaleString("es-CO")}`;
      } else {
        updateCartStatus(result.error || "No fue posible actualizar", "danger");
      }
    });
  });

  document.querySelectorAll(".remove-item").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const index = Number(btn.dataset.index);
      if (isNaN(index)) return;
      const result = await removeItem(index);
      if (result.success) {
        updateTotalUI(result.total_price, result.total_items);
        btn.closest("tr").remove();
        reindexCart();
        updateCartStatus("Producto eliminado", "success");
      } else {
        updateCartStatus(result.error || "No fue posible eliminar", "danger");
      }
    });
  });
}

/* ══════════════════════════════════════════
   BOTÓN CHECKOUT
══════════════════════════════════════════ */
function initCheckoutButton() {
  const checkout = document.getElementById("checkout-btn");
  if (!checkout) return;
  checkout.addEventListener("click", () => {
    window.location.href = "/confirmacion";
  });
}

/* ══════════════════════════════════════════
   CALIFICACIONES (ESTRELLAS)
══════════════════════════════════════════ */
function initEstrellas() {
  document.querySelectorAll(".estrellas-carrusel").forEach((contenedor) => {
    let seleccionada = 0;

    contenedor.querySelectorAll("span").forEach((star) => {
      star.addEventListener("mouseover", function () {
        const val = parseInt(this.dataset.val);
        contenedor.querySelectorAll("span").forEach((s) => {
          s.classList.toggle("activa", parseInt(s.dataset.val) <= val);
        });
      });

      star.addEventListener("mouseout", function () {
        contenedor.querySelectorAll("span").forEach((s) => {
          s.classList.toggle("activa", parseInt(s.dataset.val) <= seleccionada);
        });
      });

      star.addEventListener("click", async function () {
        seleccionada = parseInt(this.dataset.val);
        const producto = contenedor.dataset.producto;

        const res = await fetch("/api/calificar", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            producto: producto,
            estrellas: seleccionada,
            comentario: "",
          }),
        });
        const data = await res.json();

        if (data.success) {
          alert(
            `¡Gracias por calificar ${producto} con ${seleccionada} estrella(s)!`,
          );
        } else if (data.error === "No autenticado") {
          alert("Debes iniciar sesión para calificar.");
        }
      });
    });
  });
}

/* ══════════════════════════════════════════
   BARRA DE BÚSQUEDA
══════════════════════════════════════════ */
function initBuscador() {
  const inputBuscar = document.getElementById("buscarProducto");
  if (!inputBuscar) return;

  const productos = document.querySelectorAll(".card");
  const carruselEl = document.querySelector(".carousel");
  const carrusel = carruselEl?.closest(".container") || carruselEl;

  const mensajeNoEncontrado = document.createElement("div");
  mensajeNoEncontrado.id = "mensajeNoEncontrado";
  mensajeNoEncontrado.textContent = "No se encontró ningún producto.";
  mensajeNoEncontrado.style.cssText = `
    display: none; text-align: center;
    margin: 20px auto; font-size: 18px; color: #777;
  `;
  inputBuscar
    .closest(".search-bar")
    .insertAdjacentElement("afterend", mensajeNoEncontrado);

  inputBuscar.addEventListener("input", function () {
    let texto = this.value.replace(/[0-9]/g, "");
    if (texto !== this.value) this.value = texto;

    const busqueda = texto.toLowerCase().trim();
    if (carrusel) carrusel.style.display = busqueda === "" ? "" : "none";

    let encontrados = 0;
    productos.forEach((producto) => {
      const nombre =
        producto.querySelector(".card-title")?.textContent.toLowerCase() || "";
      const descripcion =
        producto.querySelector(".card-text")?.textContent.toLowerCase() || "";
      const coincide =
        nombre.includes(busqueda) || descripcion.includes(busqueda);
      if (coincide) encontrados++;
      const columna = producto.closest(".col-md-3") || producto;
      columna.style.display = coincide ? "" : "none";
    });

    mensajeNoEncontrado.style.display =
      busqueda !== "" && encontrados === 0 ? "block" : "none";
  });
}

/* ══════════════════════════════════════════
   INICIALIZACIÓN — UN SOLO DOMContentLoaded
══════════════════════════════════════════ */
document.addEventListener("DOMContentLoaded", async () => {
  await loadCartCount(); // carga el badge desde el servidor
  initAddToCartButtons();
  initCartTable();
  initCheckoutButton();
  initEstrellas();
  initBuscador();
});

/* ══════════════════════════════════════════
   PAGESHOW — actualiza badge al volver con botón "atrás"
   
══════════════════════════════════════════ */
window.addEventListener("pageshow", async (e) => {
  // e.persisted = true cuando la página viene del caché (botón atrás)
  await loadCartCount();
});
