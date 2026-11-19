package dev.observabilitylab.orders;

import java.util.logging.Level;
import java.util.logging.Logger;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.metrics.LongCounter;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private static final Logger logger = Logger.getLogger(OrderController.class.getName());
    private final String inventoryUrl;
    private final Tracer tracer = GlobalOpenTelemetry.getTracer("orders.business");
    private final LongCounter acceptedOrders = GlobalOpenTelemetry.getMeter("orders.business")
            .counterBuilder("orders.accepted")
            .setDescription("Number of orders accepted by the orders service")
            .setUnit("{order}")
            .build();
    private final LongCounter rejectedOrders = GlobalOpenTelemetry.getMeter("orders.business")
            .counterBuilder("orders.rejected")
            .setDescription("Number of orders rejected because inventory is unavailable")
            .setUnit("{order}")
            .build();

    public OrderController(@Value("${inventory.url:http://localhost:8000}") String inventoryUrl) {
        this.inventoryUrl = inventoryUrl;
    }

    @PostMapping
    public OrderResponse create(@RequestBody OrderRequest request) {
        if (request.quantity() < 1 || request.sku() == null || request.sku().isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "sku and positive quantity are required");
        }

        Span span = tracer.spanBuilder("orders.submit").startSpan();
        try (Scope ignored = span.makeCurrent()) {
            span.setAttribute("order.quantity", request.quantity());
            span.setAttribute("order.sku", request.sku());
            InventoryResponse inventory = checkInventory(request);
            String status = inventory.available() ? "accepted" : "rejected";
            if (inventory.available()) {
                acceptedOrders.add(1);
            } else {
                rejectedOrders.add(1);
            }
            span.setAttribute("order.status", status);
            span.setAttribute("inventory.available", inventory.available());
            span.setAttribute("inventory.stockout_risk", inventory.stockoutRisk());
            return new OrderResponse(status, request.sku(), request.quantity(), inventory.available(),
                    inventory.stockoutRisk(), inventory.riskLabel());
        } catch (RuntimeException exception) {
            logger.log(Level.WARNING, "Inventory service call failed", exception);
            span.recordException(exception);
            span.setStatus(io.opentelemetry.api.trace.StatusCode.ERROR);
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "inventory service call failed", exception);
        } finally {
            span.end();
        }
    }

    private InventoryResponse checkInventory(OrderRequest request) {
        try {
            byte[] body = inventoryRequestJson(request).getBytes(StandardCharsets.UTF_8);
            HttpURLConnection connection = (HttpURLConnection) new URL(inventoryUrl + "/inventory/check").openConnection();
            connection.setRequestMethod("POST");
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            connection.setDoOutput(true);
            connection.setFixedLengthStreamingMode(body.length);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(body);
            }
            int status = connection.getResponseCode();
            InputStream responseStream = status < 400 ? connection.getInputStream() : connection.getErrorStream();
            String responseBody;
            try (responseStream) {
                responseBody = new String(responseStream.readAllBytes(), StandardCharsets.UTF_8);
            }
            if (status < 200 || status >= 300) {
                throw new IllegalStateException("inventory returned HTTP " + status + ": " + responseBody);
            }
            return new InventoryResponse(Boolean.parseBoolean(jsonField(responseBody, "available")),
                    Double.parseDouble(jsonField(responseBody, "stockoutRisk")), jsonField(responseBody, "riskLabel"));
        } catch (IOException exception) {
            throw new IllegalStateException("inventory request could not be completed", exception);
        }
    }

    private static String jsonField(String body, String name) {
        Matcher matcher = Pattern.compile("\\\"" + Pattern.quote(name)
                + "\\\"\\s*:\\s*(?:\\\"([^\\\"]*)\\\"|([^,}\\s]+))").matcher(body);
        if (!matcher.find()) {
            throw new IllegalStateException("inventory response is missing " + name);
        }
        return matcher.group(1) != null ? matcher.group(1) : matcher.group(2);
    }

    private static String inventoryRequestJson(OrderRequest request) {
        String escapedSku = request.sku().replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
        return "{\"sku\":\"" + escapedSku + "\",\"quantity\":" + request.quantity()
                + ",\"dailyDemand\":" + request.dailyDemand() + ",\"onHand\":" + request.onHand()
                + ",\"leadDays\":" + request.leadDays() + ",\"demandVolatility\":"
                + request.demandVolatility() + "}";
    }

    @GetMapping("/health")
    public HealthResponse health() {
        return new HealthResponse("UP", "orders");
    }

    public record OrderRequest(String sku, int quantity, double dailyDemand, double onHand,
                               double leadDays, double demandVolatility) {}
    public record InventoryResponse(boolean available, double stockoutRisk, String riskLabel) {}
    public record OrderResponse(String status, String sku, int quantity, boolean inventoryAvailable,
                                double stockoutRisk, String riskLabel) {}
    public record HealthResponse(String status, String service) {}
}
