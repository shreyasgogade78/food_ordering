(function () {
  if (!document.querySelector(".food-app")) return;

  const state = {
    categories: [],
    menu: [],
    cart: { items: [], total: 0 },
    isGuest: document.querySelector(".food-app").dataset.user === "Guest",
  };

  const money = (value) => `₹${Number(value || 0).toFixed(0)}`;

  function call(method, args = {}) {
    return frappe.call({
      method: `food_ordering.api.${method}`,
      args,
    }).then((response) => response.message);
  }

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function loadCategories() {
    state.categories = await call("get_categories");
    const select = document.querySelector("#category-filter");
    state.categories.forEach((category) => {
      const option = document.createElement("option");
      option.value = category.name;
      option.textContent = category.category_name;
      select.appendChild(option);
    });
  }

  async function loadMenu() {
    const search = document.querySelector("#food-search").value;
    const category = document.querySelector("#category-filter").value;
    const vegan = document.querySelector("#vegan-filter").checked ? "1" : "";
    const spicy = document.querySelector("#spicy-filter").checked ? "1" : "";
    state.menu = await call("get_menu", { search, category, vegan, spicy });
    renderMenu();
  }

  async function loadCart() {
    if (state.isGuest) {
      renderGuestCart();
      return;
    }
    state.cart = await call("get_cart");
    renderCart();
  }

  function renderMenu() {
    const grid = document.querySelector("#food-grid");
    if (!state.menu.length) {
      grid.innerHTML = '<div class="empty-state">No foods found.</div>';
      return;
    }

    grid.innerHTML = state.menu
      .map((item) => {
        const tags = [
          item.is_vegan ? "Vegan" : "",
          item.is_spicy ? `Spicy${item.spicy_level ? `: ${item.spicy_level}` : ""}` : "",
          item.diet_tags || "",
        ]
          .filter(Boolean)
          .join(" • ");

        return `
          <article class="food-card">
            <div class="food-image">
              ${item.image ? `<img src="${escapeHtml(item.image)}" alt="${escapeHtml(item.item_name)}" loading="lazy" onerror="this.hidden=true;this.nextElementSibling.hidden=false">` : ""}
              <span class="food-image-fallback" ${item.image ? "hidden" : ""}>Photo unavailable</span>
              <span class="food-category">${escapeHtml(item.category)}</span>
            </div>
            <div class="food-card-body">
              <div class="food-card-top">
                <h3>${escapeHtml(item.item_name)}</h3>
                <strong class="food-price">${money(item.price)}</strong>
              </div>
              <p>${escapeHtml(item.description)}</p>
              <div class="food-meta">
                <span>${item.calories || 0} cal</span>
                <span>${item.protein || 0}g protein</span>
                <span>${item.carbs || 0}g carbs</span>
              </div>
              <div class="food-tags">${escapeHtml(tags)}</div>
              <button class="food-button add-cart" type="button" data-item="${escapeHtml(item.name)}">Add to Cart</button>
            </div>
          </article>
        `;
      })
      .join("");
  }

  function renderGuestCart() {
    document.querySelector("#cart-items").innerHTML = '<div class="empty-state">Login to add items to cart.</div>';
    document.querySelector("#cart-total").textContent = money(0);
  }

  function renderCart() {
    const wrapper = document.querySelector("#cart-items");
    if (!state.cart.items.length) {
      wrapper.innerHTML = '<div class="empty-state">Cart is empty.</div>';
      document.querySelector("#cart-total").textContent = money(0);
      return;
    }

    wrapper.innerHTML = state.cart.items
      .map(
        (item) => `
        <div class="cart-row">
          <div>
            <strong>${escapeHtml(item.item_name)}</strong>
            <span>${money(item.price)} each</span>
          </div>
          <div class="cart-actions">
            <button type="button" class="qty-btn" data-cart="${escapeHtml(item.name)}" data-qty="${item.quantity - 1}">-</button>
            <span>${item.quantity}</span>
            <button type="button" class="qty-btn" data-cart="${escapeHtml(item.name)}" data-qty="${item.quantity + 1}">+</button>
          </div>
        </div>
      `
      )
      .join("");
    document.querySelector("#cart-total").textContent = money(state.cart.total);
  }

  function addChatMessage(text, type) {
    const wrapper = document.querySelector("#chat-messages");
    const message = document.createElement("div");
    message.className = type === "user" ? "user-message" : "bot-message";
    message.textContent = text;
    wrapper.appendChild(message);
    wrapper.scrollTop = wrapper.scrollHeight;
  }

  function bindEvents() {
    document.querySelector("#food-search").addEventListener("input", frappe.utils.debounce(loadMenu, 300));
    document.querySelector("#category-filter").addEventListener("change", loadMenu);
    document.querySelector("#vegan-filter").addEventListener("change", loadMenu);
    document.querySelector("#spicy-filter").addEventListener("change", loadMenu);

    document.querySelector("#food-grid").addEventListener("click", async (event) => {
      const button = event.target.closest(".add-cart");
      if (!button) return;
      if (state.isGuest) {
        window.location.href = "/login?redirect-to=/food-menu";
        return;
      }
      state.cart = await call("add_to_cart", { food_item: button.dataset.item, quantity: 1 });
      renderCart();
    });

    document.querySelector("#cart-items").addEventListener("click", async (event) => {
      const button = event.target.closest(".qty-btn");
      if (!button) return;
      state.cart = await call("update_cart_item", { cart_item: button.dataset.cart, quantity: button.dataset.qty });
      renderCart();
    });

    document.querySelector("#clear-cart").addEventListener("click", async () => {
      if (state.isGuest) return;
      state.cart = await call("clear_cart");
      renderCart();
    });

    document.querySelector("#chat-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = document.querySelector("#chat-input");
      const question = input.value.trim();
      if (!question) return;
      addChatMessage(question, "user");
      input.value = "";
      const response = await call("chatbot", { message: question });
      addChatMessage(response.answer, "bot");
    });
  }

  async function init() {
    bindEvents();
    await loadCategories();
    await loadMenu();
    await loadCart();
  }

  frappe.ready(init);
})();
