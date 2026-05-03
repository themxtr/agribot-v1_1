import torch
import torch.nn as nn
import torch.nn.functional as F

class SimAM(nn.Module):
    def __init__(self, channels, e_lambda=1e-4): # Added channels arg for compatibility
        super(SimAM, self).__init__()
        self.activaton = nn.Sigmoid()
        self.e_lambda = e_lambda

    def forward(self, x):
        b, c, h, w = x.size()
        n = w * h - 1
        x_minus_mu_square = (x - x.mean(dim=[2, 3], keepdim=True)).pow(2)
        y = x_minus_mu_square / (4 * (x_minus_mu_square.sum(dim=[2, 3], keepdim=True) / n + self.e_lambda)) + 0.5
        return x * self.activaton(y)

class EMA(nn.Module):
    """
    EMA: Efficient Multi-Scale Attention Module
    """
    def __init__(self, channels, factor=32):
        super(EMA, self).__init__()
        self.groups = factor
        self.conv1x1 = nn.Conv2d(channels // factor, channels // factor, kernel_size=1)
        self.conv3x3 = nn.Conv2d(channels // factor, channels // factor, kernel_size=3, padding=1)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.gn = nn.GroupNorm(channels // factor, channels // factor)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        b, c, h, w = x.size()
        group_x = x.view(b * self.groups, -1, h, w)  # [b*g, c/g, h, w]
        
        x1 = self.pool(group_x)
        x1 = self.conv1x1(x1)
        x1 = self.sigmoid(x1)
        
        x2 = self.conv3x3(group_x)
        x2 = self.sigmoid(x2)
        
        out = group_x * x1 + group_x * x2
        return out.view(b, c, h, w)

class BiFPN_Concat(nn.Module):
    def __init__(self, dimension=256):
        super(BiFPN_Concat, self).__init__()
        self.w = nn.Parameter(torch.ones(3, dtype=torch.float32), requires_grad=True)
        self.epsilon = 0.0001

    def forward(self, x):
        # x is a list of tensors
        w = self.w[:len(x)]
        weight = w / (torch.sum(w, dim=0) + self.epsilon)
        out = 0
        for i in range(len(x)):
            out += weight[i] * x[i]
        return out

class C2f_Attention(nn.Module):
    """Standard C2f with SimAM and EMA attention."""
    def __init__(self, c1, c2, n=1, shortcut=False, g=1, e=0.5):
        super().__init__()
        from ultralytics.nn.modules import C2f
        self.c2f = C2f(c1, c2, n, shortcut, g, e)
        self.attention = nn.Sequential(
            SimAM(c2),
            EMA(c2)
        )

    def forward(self, x):
        return self.attention(self.c2f(x))

class MPDIoU(nn.Module):
    """
    MPDIoU: A Loss for Bounding Box Regression
    """
    def __init__(self):
        super(MPDIoU, self).__init__()

    def forward(self, pred, target, eps=1e-7):
        # pred, target: [x1, y1, x2, y2]
        d1 = (pred[:, 0] - target[:, 0])**2 + (pred[:, 1] - target[:, 1])**2
        d2 = (pred[:, 2] - target[:, 2])**2 + (pred[:, 3] - target[:, 3])**2
        
        # Standard IoU part
        inter_x1 = torch.max(pred[:, 0], target[:, 0])
        inter_y1 = torch.max(pred[:, 1], target[:, 1])
        inter_x2 = torch.min(pred[:, 2], target[:, 2])
        inter_y2 = torch.min(pred[:, 3], target[:, 3])
        
        inter_area = torch.clamp(inter_x2 - inter_x1, min=0) * torch.clamp(inter_y2 - inter_y1, min=0)
        area_pred = (pred[:, 2] - pred[:, 0]) * (pred[:, 3] - pred[:, 1])
        area_target = (target[:, 2] - target[:, 0]) * (target[:, 3] - target[:, 1])
        union = area_pred + area_target - inter_area + eps
        iou = inter_area / union
        
        # MPDIoU penalty
        # h, w of input image squared (assuming normalized, h=w=1)
        # But usually we use the enclosing box diag or similar.
        # Original MPDIoU: R_MPDIoU = d1/w^2 + d2/h^2
        # If normalized:
        return 1 - iou + d1 + d2
