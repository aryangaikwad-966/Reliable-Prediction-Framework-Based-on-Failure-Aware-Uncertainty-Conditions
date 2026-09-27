import { describe, expect, it, beforeAll } from "vitest";
import { buildDecision, calculateRisk, classifyFailure, evaluateRegression } from "./research";

describe("Integration tests for prediction pipeline", () => {
  describe("Full prediction workflow", () => {
    it("should generate a complete prediction record with all signals", () => {
      const input = {
        commodity: "Tomato",
        market: "Lasalgaon",
        variety: "Local",
        horizon: 7,
      };
      
      const signals = {
        modelUncertainty: 0.25,
        historicalFailureRisk: 0.15,
        noveltyScore: 0.18,
        driftScore: 0.12,
        missingInformation: 0.05,
        contextRisk: 0.08,
      };
      
      const result = buildDecision(450, signals, { 
        reliabilityThreshold: 0.7, 
        isDemo: false, 
        context: input 
      });
      
      expect(result).toHaveProperty("id");
      expect(result).toHaveProperty("commodity", "Tomato");
      expect(result).toHaveProperty("market", "Lasalgaon");
      expect(result).toHaveProperty("variety", "Local");
      expect(result).toHaveProperty("horizon", 7);
      expect(result).toHaveProperty("basePrediction", 450);
      expect(result).toHaveProperty("reliability");
      expect(result).toHaveProperty("failureRisk");
      expect(result).toHaveProperty("decision");
      expect(result).toHaveProperty("signals");
      expect(result).toHaveProperty("reasons");
      expect(result).toHaveProperty("createdAt");
      expect(result).toHaveProperty("isDemo", false);
      
      // Check that reliability and failure risk sum to 1
      expect(result.reliability + result.failureRisk).toBeCloseTo(1, 4);
    });
    
    it("should accept prediction when reliability is above threshold", () => {
      const result = buildDecision(500, {
        modelUncertainty: 0.1,
        historicalFailureRisk: 0.1,
        noveltyScore: 0.1,
        driftScore: 0.1,
        missingInformation: 0.0,
        contextRisk: 0.0,
      }, { reliabilityThreshold: 0.7 });
      
      expect(result.decision).toBe("ACCEPTED");
      expect(result.prediction).toBe(500);
      expect(result.prediction).not.toBeNull();
    });
    
    it("should abstain when reliability is below threshold", () => {
      const result = buildDecision(500, {
        modelUncertainty: 0.8,
        historicalFailureRisk: 0.9,
        noveltyScore: 0.85,
        driftScore: 0.9,
        missingInformation: 0.5,
        contextRisk: 0.7,
      }, { reliabilityThreshold: 0.7 });
      
      expect(result.decision).toBe("ABSTAINED");
      expect(result.prediction).toBeNull();
      expect(result.reasons.length).toBeGreaterThan(0);
    });
    
    it("should generate appropriate abstention reasons", () => {
      const result = buildDecision(500, {
        modelUncertainty: 0.7,
        historicalFailureRisk: 0.6,
        noveltyScore: 0.7,
        driftScore: 0.1,
        missingInformation: 0.1,
        contextRisk: 0.1,
      }, { reliabilityThreshold: 0.7 });
      
      expect(result.decision).toBe("ABSTAINED");
      expect(result.reasons).toContain("Model uncertainty is elevated");
      expect(result.reasons).toContain("Similar historical cases showed high failure rates");
      expect(result.reasons).toContain("Current context is unusual relative to training data");
    });
  });
  
  describe("Failure classification workflow", () => {
    it("should classify normal failures correctly", () => {
      const severity = classifyFailure(5, 0.05);
      expect(severity).toBe("NORMAL");
    });
    
    it("should classify moderate failures correctly", () => {
      const severity = classifyFailure(50, 0.15);
      expect(severity).toBe("MODERATE");
    });
    
    it("should classify significant failures correctly", () => {
      const severity = classifyFailure(100, 0.3);
      expect(severity).toBe("SIGNIFICANT");
    });
    
    it("should classify high failures correctly", () => {
      const severity = classifyFailure(200, 0.6);
      expect(severity).toBe("HIGH");
    });
  });
  
  describe("Evaluation metrics workflow", () => {
    it("should calculate regression metrics correctly", () => {
      const actual = [100, 200, 300, 400, 500];
      const predicted = [110, 190, 310, 390, 510];
      
      const metrics = evaluateRegression(actual, predicted);
      
      expect(metrics.mae).toBeCloseTo(10, 4);
      expect(metrics.rmse).toBeCloseTo(10, 4);
      expect(metrics.r2).toBeGreaterThan(0.95);
      expect(metrics.mape).toBeCloseTo(0.05, 2);
    });
    
    it("should handle empty arrays gracefully", () => {
      const metrics = evaluateRegression([], []);
      
      expect(metrics.mae).toBeNull();
      expect(metrics.rmse).toBeNull();
      expect(metrics.r2).toBeNull();
      expect(metrics.mape).toBeNull();
    });
    
    it("should handle mismatched arrays gracefully", () => {
      const metrics = evaluateRegression([100, 200], [100]);
      
      expect(metrics.mae).toBeNull();
      expect(metrics.rmse).toBeNull();
      expect(metrics.r2).toBeNull();
    });
  });
  
  describe("Risk calculation workflow", () => {
    it("should calculate zero risk for perfect signals", () => {
      const risk = calculateRisk({
        modelUncertainty: 0,
        historicalFailureRisk: 0,
        noveltyScore: 0,
        driftScore: 0,
        missingInformation: 0,
        contextRisk: 0,
      });
      
      expect(risk).toBe(0);
    });
    
    it("should calculate maximum risk for worst signals", () => {
      const risk = calculateRisk({
        modelUncertainty: 1,
        historicalFailureRisk: 1,
        noveltyScore: 1,
        driftScore: 1,
        missingInformation: 1,
        contextRisk: 1,
      });
      
      expect(risk).toBe(1);
    });
    
    it("should clamp risk to [0, 1] range", () => {
      const risk1 = calculateRisk({
        modelUncertainty: 2,
        historicalFailureRisk: 0,
        noveltyScore: 0,
        driftScore: 0,
        missingInformation: 0,
        contextRisk: 0,
      });
      
      const risk2 = calculateRisk({
        modelUncertainty: -1,
        historicalFailureRisk: 0,
        noveltyScore: 0,
        driftScore: 0,
        missingInformation: 0,
        contextRisk: 0,
      });
      
      expect(risk1).toBe(1);
      expect(risk2).toBe(0);
    });
    
    it("should use weighted average for risk calculation", () => {
      const risk = calculateRisk({
        modelUncertainty: 0.5,
        historicalFailureRisk: 0.5,
        noveltyScore: 0.5,
        driftScore: 0.5,
        missingInformation: 0.5,
        contextRisk: 0.5,
      });
      
      // All weights sum to 1, so with all signals at 0.5, risk should be 0.5
      expect(risk).toBeCloseTo(0.5, 4);
    });
  });
  
  describe("Selective prediction edge cases", () => {
    it("should handle zero division in reliability calculation", () => {
      const result = buildDecision(0, {
        modelUncertainty: 0.5,
        historicalFailureRisk: 0.5,
        noveltyScore: 0.5,
        driftScore: 0.5,
        missingInformation: 0.5,
        contextRisk: 0.5,
      }, { reliabilityThreshold: 0.7 });
      
      expect(result.reliability).toBeGreaterThanOrEqual(0);
      expect(result.reliability).toBeLessThanOrEqual(1);
      expect(result.failureRisk).toBeGreaterThanOrEqual(0);
      expect(result.failureRisk).toBeLessThanOrEqual(1);
    });
    
    it("should handle extreme predictions", () => {
      const result = buildDecision(1000000, {
        modelUncertainty: 0.1,
        historicalFailureRisk: 0.1,
        noveltyScore: 0.1,
        driftScore: 0.1,
        missingInformation: 0.0,
        contextRisk: 0.0,
      }, { reliabilityThreshold: 0.7 });
      
      expect(result.decision).toBe("ACCEPTED");
      expect(result.prediction).toBe(1000000);
    });
    
    it("should handle negative predictions (should not occur in practice)", () => {
      const result = buildDecision(-100, {
        modelUncertainty: 0.1,
        historicalFailureRisk: 0.1,
        noveltyScore: 0.1,
        driftScore: 0.1,
        missingInformation: 0.0,
        contextRisk: 0.0,
      }, { reliabilityThreshold: 0.7 });
      
      expect(result.decision).toBe("ACCEPTED");
      expect(result.prediction).toBe(-100);
    });
  });
});